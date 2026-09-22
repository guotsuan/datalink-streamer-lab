"""Small process group for a systemd user unit. No root privileges needed."""
import os
import logging
from logging.handlers import RotatingFileHandler
import signal
import subprocess
import threading
import time
from pathlib import Path
from fixtures import ROOT, STORAGE, initialise

initialise()
(ROOT / "logs").mkdir(exist_ok=True)
env = dict(os.environ)
env.update({"OTEL_SDK_DISABLED": "true", "LOG_LEVEL": "WARNING",
    "OTEL_TRACES_EXPORTER": "none", "OTEL_METRICS_EXPORTER": "none", "OTEL_LOGS_EXPORTER": "none",
    "DATA_MANAGEMENT_API_URL": "http://127.0.0.1:18080/mock/v1",
    "DATA_MANAGEMENT_CLIENT_ID": "lab-client", "DATA_MANAGEMENT_CLIENT_SECRET": "synthetic-not-secret",
    "DATA_MANAGEMENT_CLIENT_SCOPES": "lab", "DATA_MANAGEMENT_CLIENT_AUDIENCE": "lab-dm",
    "IAM_TOKEN_ENDPOINT": "http://127.0.0.1:18080/mock/token", "IVOA_AUTHORITY": "lab.invalid",
    "IAM_WELLKNOWN_ENDPOINT": "http://localhost:18080/mock/.well-known/openid-configuration",
    "PERMISSIONS_API_URL": "http://127.0.0.1:18080/mock/papi", "PERMISSIONS_SERVICE_NAME": "product-streamer-api",
    "PERMISSIONS_SERVICE_VERSION": "1", "STORAGE_BASE_PATH": str(STORAGE),
    "AAPI_URL": "http://localhost:18080/mock/aapi", "DISABLE_AUTHENTICATION": "no",
    "SERVICE_VERSION": "pinned-lab"})
services = [(".venv", "app:app", 18080),
            (".venv-datalink", "ska_src_dm_datalink.rest.server:app", 18081),
            (".venv-streamer", "ska_src_dm_product_service.rest.server:app", 18082)]
children = []
stopping = False


def capture(child, name):
    log = logging.getLogger(name)
    log.setLevel(logging.INFO)
    handler = RotatingFileHandler(ROOT / "logs" / (name + ".log"), maxBytes=2*1024*1024, backupCount=2)
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    log.addHandler(handler)
    for line in child.stdout:
        log.info(line.rstrip())


def stop(*_):
    global stopping
    stopping = True
    for child in children:
        if child.poll() is None:
            child.terminate()


signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)
try:
    for venv, module, port in services:
        cmd = [str(ROOT / venv / "bin/python"), "-m", "uvicorn", module,
               "--host", "127.0.0.1", "--port", str(port), "--no-access-log"]
        child = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        children.append(child)
        threading.Thread(target=capture, args=(child, str(port)), daemon=True).start()
    while not stopping:
        if any(c.poll() is not None for c in children):
            raise RuntimeError("A service exited; stopping the group so systemd can restart it")
        time.sleep(1)
finally:
    stop()
    for child in children:
        try:
            child.wait(timeout=12)
        except subprocess.TimeoutExpired:
            child.kill()
