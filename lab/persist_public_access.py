"""Remove the expiry only on the explicit user request to keep this lab open."""
import json
import os
from pathlib import Path
from fixtures import ROOT

if ROOT != Path("/home/gq/datalink-streamer-lab"):
    raise SystemExit("Run only in the deployed VM laboratory")
config_path = ROOT / "public-access.json"
credentials_path = ROOT / "public-access-credentials.txt"
for path in (config_path, credentials_path):
    if path.is_symlink() or not path.is_file():
        raise SystemExit("Missing or unexpected configuration file")
config = json.loads(config_path.read_text())
if config.get("origin") != "http://64.176.188.89:18080":
    raise SystemExit("Unexpected origin")
config["expires"] = None
lines = credentials_path.read_text().splitlines()
if sum(line.startswith("Expires (UTC): ") for line in lines) != 1:
    raise SystemExit("Unexpected credentials format")
lines = ["Expires (UTC): none; stays open until explicitly disabled" if line.startswith("Expires (UTC): ") else line for line in lines]
for path, content in [(config_path, json.dumps(config, indent=2)), (credentials_path, "\n".join(lines) + "\n")]:
    temporary = path.with_suffix(path.suffix + ".persist-update")
    with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as stream:
        stream.write(content)
    os.replace(temporary, path)
print("Public expiry removed; password and cookie signing key unchanged")
