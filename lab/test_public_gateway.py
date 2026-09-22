"""Isolated auth regression checks; no real credentials or network calls."""
import asyncio
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import patch

import httpx


async def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name("public_gateway.py")
    password = "synthetic-regression-password"
    salt = bytes.fromhex("12" * 16)
    config = {"origin": "http://64.176.188.89:18080", "expires": None,
              "cookie_key": "34" * 32, "salt": salt.hex(),
              "password_hash": hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1).hex()}
    spec = importlib.util.spec_from_file_location("gateway_under_test", path)
    module = importlib.util.module_from_spec(spec)
    with patch.object(Path, "read_text", return_value=json.dumps(config)):
        spec.loader.exec_module(module)
    checks = []

    def check(name, condition):
        assert condition, name
        checks.append(name)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=module.app), base_url=config["origin"]) as c:
        root = await c.get("/")
        check("Anonymous root redirects to login", root.status_code == 303 and root.headers["location"] == "/login")
        form = await c.get("/login")
        check("Login form available", form.status_code == 200 and 'action="/login"' in form.text)
        check("Browser form origin preserved", form.headers.get("referrer-policy") == "same-origin")
        check("Login form not cached", form.headers.get("cache-control") == "no-store")
        for origin in ["null", "https://example.invalid"]:
            r = await c.post("/login", headers={"Origin": origin}, data={"password": password})
            check(f"Untrusted origin denied: {origin}", r.status_code == 403)
        headers = {"Origin": config["origin"]}
        r = await c.post("/login", headers={**headers, "Sec-Fetch-Site": "cross-site"}, data={"password": password})
        check("Cross-site login denied", r.status_code == 403)
        r = await c.post("/login", headers=headers, data={"password": "wrong"})
        check("Wrong password denied", r.status_code == 401)
        check("Retry form origin preserved", r.headers.get("referrer-policy") == "same-origin")
        r = await c.post("/login", headers=headers, data={"password": password})
        check("Same-origin login succeeds", r.status_code == 303 and r.headers["location"] == "/")
        check("Cookie flags unchanged", "HttpOnly" in r.headers["set-cookie"] and "SameSite=strict" in r.headers["set-cookie"])
        cookie = c.cookies.get("lab_session")
        check("Session valid", module.session_ok(cookie))
        check("Tampered session denied", not module.session_ok(cookie + "x"))
    print(json.dumps({"passed": len(checks), "checks": checks}, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
