"""Create a single 24-hour public test window; never overwrite credentials."""
import hashlib
import json
import os
import secrets
import time
from datetime import datetime, timezone
from fixtures import ROOT

paths = [ROOT / "public-access.json", ROOT / "public-access-credentials.txt"]
if any(path.exists() for path in paths):
    raise SystemExit("Public configuration already exists; refusing to reset its expiry or credentials")
password = secrets.token_urlsafe(20)
salt = secrets.token_hex(16)
expires = int(time.time()) + 24 * 3600
config = {"origin": "http://64.176.188.89:18080", "expires": expires,
          "salt": salt, "password_hash": hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex(),
          "cookie_key": secrets.token_hex(32)}
expiry = datetime.fromtimestamp(expires, timezone.utc).isoformat()
for path, content in [(paths[0], json.dumps(config, indent=2)),
                      (paths[1], f"URL: {config['origin']}\nPassword: {password}\nExpires (UTC): {expiry}\nHTTP is not encrypted. Synthetic test data only.\n")]:
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as f:
        f.write(content)
print("Public test window expires (UTC): " + expiry)
