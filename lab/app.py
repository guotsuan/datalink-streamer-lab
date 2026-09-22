"""Loopback-only test portal and explicitly simulated upstream dependencies.

DataLink and Product Streamer run unmodified in separate processes. The mock
DMAPI and PAPI below are fixtures, NOT implementations of SRCNet services.
"""
import asyncio
import hashlib
import io
import json
import time
import tarfile
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask
from starlette.middleware.trustedhost import TrustedHostMiddleware
from fixtures import ROOT, STORAGE, SCOPE, DL_COMMIT, PS_COMMIT, contents, manifest, public_base

app = FastAPI(title="DataLink / Streamer test laboratory")
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1"])
BASE = public_base()
DL = "http://127.0.0.1:18081"
PS = "http://127.0.0.1:18082"
TOKEN = "lab-service-token"  # Public synthetic fixture, not an SKA credential.
NS = {"v": "http://www.ivoa.net/xml/VOTable/v1.3"}
lock = asyncio.Lock()


@app.middleware("http")
async def browser_boundary(request, call_next):
    origin = request.headers.get("origin")
    if origin and origin not in {BASE, "http://localhost:18080", "http://127.0.0.1:18080"}:
        return JSONResponse({"detail": "Only same-origin laboratory requests are allowed"}, 403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = "default-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'none'"
    return response


@app.get("/")
async def index():
    return FileResponse(ROOT / "static/index.html")


@app.get("/lab/info")
async def info():
    return {"mode": "Official services + simulated dependencies", "datalink_commit": DL_COMMIT,
            "streamer_commit": PS_COMMIT, "storage": str(STORAGE), "fixtures": manifest(),
            "dataset": f"{SCOPE}:dataset", "synthetic_token": TOKEN, "public_origin": BASE,
            "limitations": ["No real IAM, PAPI, DMAPI, SCAPI or Rucio",
                            "No production readiness or complete IVOA conformance claim",
                            "Internal services are loopback only; public access, if enabled, is temporary and password-gated"]}


@app.get("/lab/status")
async def status():
    async with httpx.AsyncClient(timeout=8, trust_env=False) as c:
        async def check(name, base):
            try:
                r = await c.get(base + "/v1/health")
                return {"service": name, "http": r.status_code, "body": r.json()}
            except Exception as e:
                return {"service": name, "http": 0, "error": type(e).__name__}
        return await asyncio.gather(check("DataLink", DL), check("Streamer", PS))


# Simulated IAM / DMAPI / PAPI. No real credentials accepted or forwarded.
@app.post("/mock/token")
async def mock_token():
    return {"access_token": "lab-dm-token", "token_type": "Bearer", "expires_in": 3600}


@app.get("/mock/.well-known/openid-configuration")
async def discovery():
    return {"issuer": BASE + "/mock", "token_endpoint": BASE + "/mock/token",
            "lab_only": True, "note": "Fixture only; no real OIDC implementation"}


@app.get("/mock/v1/ping")
@app.get("/mock/papi/ping")
async def mock_ping():
    return {"status": "UP", "simulated": True}


@app.post("/mock/papi/authorise/route/{service}")
async def authorise(service: str, request: Request, token: str = ""):
    if token == "lab-raw-token":
        raise HTTPException(401, "incorrect audience (simulated)")
    if token not in {TOKEN, "lab-denied-token"}:
        raise HTTPException(401, "invalid token (simulated)")
    body = await request.json()
    return {"is_authorised": token == TOKEN and body.get("namespace") in {None, SCOPE},
            "simulated": True}


def names_for(scope, name):
    if scope != SCOPE:
        raise HTTPException(404, "Unknown synthetic namespace")
    if name == "dataset":
        return ["image.fits", "readme.txt", "metadata.json"]
    if name not in contents():
        raise HTTPException(404, "Unknown synthetic DID")
    return [name]


@app.get("/mock/v1/data/locate/{scope}/{name:path}")
async def locate(scope: str, name: str, request: Request):
    names = names_for(scope, name)
    if request.headers.get("authorization") != "Bearer lab-dm-token":
        raise HTTPException(401, "Synthetic DM token required")
    return [{"identifier": "LAB_LOCAL_RSE", "is_dataset": name == "dataset",
             "replicas": [f"{BASE}/fixtures/{SCOPE}/{n}" for n in names],
             "colocated_services": [{"type": "product_streamer", "prefix": urlsplit(BASE).scheme,
                 "host": urlsplit(BASE).hostname, "port": urlsplit(BASE).port or 80, "path": "streamer/v1/data/product",
                 "is_force_disabled": False}]}]


@app.get("/mock/v1/metadata/{scope}/{name:path}")
async def metadata(scope: str, name: str):
    names = names_for(scope, name)
    return {"obs_id": "Synthetic laboratory fixture", "content_type": "application/octet-stream",
            "content_length": sum(len(contents()[n]) for n in names), "datalinks": "[]"}


@app.get("/fixtures/{scope}/{name}")
async def fixture(scope: str, name: str):
    names_for(scope, name)
    if name == "dataset":
        raise HTTPException(404, "Use the Streamer for datasets")
    return FileResponse(STORAGE / scope / name)


async def bounded_body(request):
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 1024 * 1024:
            raise HTTPException(413, "Lab request limit is 1 MiB")
    return bytes(body)


def check_paths(body, content_type):
    """Extra lab gateway guard; not attributed to the upstream service."""
    paths = []
    try:
        if "xml" in content_type:
            if b"<!DOCTYPE" in body.upper() or b"<!ENTITY" in body.upper():
                raise HTTPException(400, "XML declarations not permitted in this lab")
            root = ET.fromstring(body)
            ids = [n.text for n in root.findall(".//v:TR/v:TD[1]", NS)]
            ids += [n.get("value") for n in root.findall(".//v:PARAM[@name='ID']", NS)]
            paths = [STORAGE / value.split("?", 1)[1] for value in ids if value and "?" in value]
        elif "json" in content_type:
            items = json.loads(body)
            if isinstance(items, list):
                paths = [Path(p["path"]) for p in items if isinstance(p, dict) and "path" in p]
    except (ValueError, TypeError, ET.ParseError):
        return  # Let the official service report malformed bodies.
    if len(paths) > 32:
        raise HTTPException(400, "Lab gateway: too many product references")
    permitted = {(STORAGE / SCOPE / name).resolve() for name in contents()}
    permitted.add((STORAGE / SCOPE / "dataset").resolve())
    for path in paths:
        resolved = path.resolve()
        if not resolved.is_relative_to(STORAGE.resolve()):
            raise HTTPException(400, "Lab gateway: path outside fixture storage")
        if resolved not in permitted:
            raise HTTPException(400, "Lab gateway: only registered synthetic fixtures are allowed")
        if resolved.exists() and resolved.is_dir():
            # Fixtures use explicit file lists; do not expose arbitrary directory walks.
            if resolved != STORAGE / SCOPE / "dataset":
                raise HTTPException(400, "Lab gateway: use the synthetic dataset DID")


@app.api_route("/{service}/{path:path}", methods=["GET", "POST"])
async def proxy(service: str, path: str, request: Request):
    allowed = {"datalink": {"v1/links", "v1/ping", "v1/health", "v1/openapi.json"},
               "streamer": {"v1/data/product", "v1/ping", "v1/health", "v1/metrics", "v1/openapi.json"}}
    if service not in allowed or path not in allowed[service]:
        raise HTTPException(404)
    if (path == "v1/data/product") != (request.method == "POST"):
        raise HTTPException(405)
    body = await bounded_body(request)
    ct = request.headers.get("content-type", "")
    if service == "streamer" and body:
        check_paths(body, ct)
    headers = {k: request.headers[k] for k in ("content-type", "authorization", "range", "if-range") if k in request.headers}
    client = httpx.AsyncClient(timeout=30, trust_env=False)
    try:
        req = client.build_request(request.method, (DL if service == "datalink" else PS) + "/" + path,
                                   params=request.query_params, headers=headers, content=body)
        response = await client.send(req, stream=True)
    except httpx.HTTPError:
        await client.aclose()
        raise HTTPException(502, "Service unavailable; check laboratory logs")
    async def close():
        await response.aclose()
        await client.aclose()
    keep = {k: v for k, v in response.headers.items() if k.lower() in
            {"content-type", "content-length", "content-disposition", "content-range", "accept-ranges", "etag", "last-modified", "www-authenticate"}}
    return StreamingResponse(response.aiter_raw(), status_code=response.status_code, headers=keep,
                             background=BackgroundTask(close))


async def run_suite():
    from smoke import run
    return await run()


# Defined before the catch-all routes in the final route ordering below.
@app.post("/lab/run")
async def run_tests():
    if lock.locked():
        raise HTTPException(409, "A test run is already in progress")
    async with lock:
        report = await run_suite()
        name = report["run_id"] + ".json"
        (ROOT / "evidence" / name).write_text(json.dumps(report, indent=2))
        return report


@app.get("/lab/reports/{name}")
async def report_file(name: str):
    if not name.endswith(".json") or len(name) != 41:
        raise HTTPException(404)
    try:
        uuid.UUID(name[:-5])
    except ValueError:
        raise HTTPException(404)
    path = ROOT / "evidence" / name
    if not path.is_file():
        raise HTTPException(404)
    return FileResponse(path, filename=name)


app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
# Generic service proxy must be after all explicit application/static routes.
proxy_route = next(r for r in app.router.routes if getattr(r, "endpoint", None) is proxy)
app.router.routes.remove(proxy_route)
app.router.routes.append(proxy_route)
