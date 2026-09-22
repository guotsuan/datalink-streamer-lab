"""Validate the public gate without printing its password or session cookie."""
import hashlib
import json
import httpx
from fixtures import ROOT, contents

config = json.loads((ROOT / "public-access.json").read_text())
password = next(line.removeprefix("Password: ") for line in (ROOT / "public-access-credentials.txt").read_text().splitlines() if line.startswith("Password: "))
checks = []


def check(label, condition):
    if not condition:
        raise AssertionError(label)
    checks.append(label)


with httpx.Client(base_url=config["origin"], timeout=60, trust_env=False) as c:
    check("Anonymous root redirects to login", c.get("/").status_code == 303)
    check("Anonymous API denied", c.get("/lab/info").status_code == 401)
    login = c.get("/login")
    check("Login form available", login.status_code == 200)
    check("Login form preserves same-origin POST identity", login.headers.get("referrer-policy") == "same-origin")
    check("Login form is not cached", login.headers.get("cache-control") == "no-store")
    check("Null-origin login remains denied", c.post("/login", headers={"Origin": "null"}).status_code == 403)
    check("Foreign-origin login remains denied", c.post("/login", headers={"Origin": "https://example.invalid"}).status_code == 403)
    browser_headers = {"Origin": config["origin"]}
    invalid = c.post("/login", headers=browser_headers, data={"password": "not-the-password"})
    check("Invalid password denied", invalid.status_code == 401)
    check("Login retry preserves same-origin policy", invalid.headers.get("referrer-policy") == "same-origin")
    check("Cross-site login remains denied", c.post("/login", headers={**browser_headers, "Sec-Fetch-Site": "cross-site"}).status_code == 403)
    r = c.post("/login", headers=browser_headers, data={"password": password})
    check("Valid password accepted", r.status_code == 303)
    check("HttpOnly / SameSite cookie", "HttpOnly" in r.headers["set-cookie"] and "SameSite=strict" in r.headers["set-cookie"])
    home = c.get("/")
    check("Signed-in homepage available", home.status_code == 200 and "text/html" in home.headers.get("content-type", ""))
    check("Other pages retain no-referrer policy", home.headers.get("referrer-policy") == "no-referrer")
    check("Mock API not publicly routable", c.post("/mock/token").status_code == 404)
    check("Cross-origin POST rejected", c.post("/lab/run", headers={"Origin": "https://example.invalid"}).status_code == 403)
    check("Both upstream services healthy", all(x["http"] == 200 for x in c.get("/lab/status").json()))
    r = c.get("/datalink/v1/links", params={"id": "lab.test:image.fits"})
    check("Public Streamer descriptor advertised", r.status_code == 200 and (config["origin"] + "/streamer/v1/data/product") in r.text)
    streamed = c.post("/streamer/v1/data/product", content=r.content, headers={"Content-Type": "application/xml", "Authorization": "Bearer lab-service-token"})
    check("Authenticated public file matches SHA-256", streamed.status_code == 200 and hashlib.sha256(streamed.content).digest() == hashlib.sha256(contents()["image.fits"]).digest())
    denied = c.post("/streamer/v1/data/product", json=[{"did": "lab.test:x", "path": "/etc/passwd"}], headers={"Authorization": "Bearer lab-service-token"})
    check("Outside-storage request rejected", denied.status_code == 400)
    report = c.post("/lab/run").json()
    check("Functional suite retains known baseline", report["passed"] == 14 and report["total"] == 15)
    result = {"public_checks": checks, "count": len(checks), "service_report": report}
    (ROOT / "evidence/public-access-verification.json").write_text(json.dumps(result, indent=2))
    print(json.dumps({"public_checks_passed": len(checks), "service_suite": f"{report['passed']}/{report['total']}", "expires": config["expires"]}))
