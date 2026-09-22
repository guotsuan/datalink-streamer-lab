#!/usr/bin/env python3
"""Public lab end-to-end tests. Python 3.9+, standard library only.

This is a lab-specific functional test, not a general IVOA client or scanner.
Passwords/cookies are kept in memory; only public fixture tokens are used.
"""
import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import getpass
import hashlib
from http.cookiejar import CookieJar
import io
import json
from pathlib import Path
import re
import sys
import tarfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import xml.etree.ElementTree as ET

DEFAULT_BASE = "http://64.176.188.89:18080"
NS = {"v": "http://www.ivoa.net/xml/VOTable/v1.3"}
MAX_RESPONSE = 16 * 1024 * 1024
TOKEN = "lab-service-token"  # Public simulated identity, never a real credential.


def fixture_bytes():
    cards = ["SIMPLE  =                    T", "BITPIX  =                    8",
             "NAXIS   =                    2", "NAXIS1  =                   16", "NAXIS2  =                   16",
             "COMMENT Synthetic test fixture; not observational data", "END"]
    fits = "".join(c.ljust(80) for c in cards).ljust(2880).encode("ascii")
    fits += bytes(range(256)) + bytes(2880 - 256)
    return {"image.fits": fits,
            "readme.txt": b"Synthetic DataLink / Product Streamer laboratory fixture.\n",
            "metadata.json": b'{"synthetic":true,"instrument":"none"}\n',
            "range.bin": bytes(range(256)) * 4096}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise AssertionError(message)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward cookies or Authorization through redirects.


@dataclass
class Response:
    code: int
    headers: object
    body: bytes

    def json(self):
        return json.loads(self.body)


class LabTest:
    def __init__(self, base, directory, timeout):
        parsed = urllib.parse.urlsplit(base)
        require(parsed.scheme in {"http", "https"} and parsed.hostname is not None,
                "Base URL must be an HTTP(S) origin")
        require(not parsed.username and not parsed.password and parsed.path in {"", "/"}
                and not parsed.query and not parsed.fragment, "Use an origin without path, query or credentials")
        self.base = base.rstrip("/")
        self.directory = directory
        self.timeout = timeout
        self.expected = fixture_bytes()
        self.cookies = CookieJar()
        self.client = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect(),
                                                  urllib.request.HTTPCookieProcessor(self.cookies))
        self.results, self.requests, self.addresses = [], [], []
        self.xmls, self.endpoints, self.standard_findings = {}, {}, []

    def url(self, path):
        return self.base + path

    def request(self, method, url, data=None, headers=None):
        require(self.origin(url) == self.origin(self.base), "Refusing request outside configured origin")
        parsed = urllib.parse.urlsplit(url)
        require(not parsed.username and not parsed.password and not parsed.fragment, "Unsafe URL")
        request_headers = {"User-Agent": "DataLink-Lab-E2E/1.0"}
        if method == "POST":
            request_headers["Origin"] = self.base
        request_headers.update(headers or {})
        request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
        start = time.monotonic()
        entry = {"method": method, "url": url}
        try:
            try:
                response = self.client.open(request, timeout=self.timeout)
            except urllib.error.HTTPError as error:
                response = error
            with response:
                body = response.read(MAX_RESPONSE + 1)
                require(len(body) <= MAX_RESPONSE, "Response exceeds 16 MiB test limit")
                entry.update(http=response.code, bytes=len(body))
                return Response(response.code, response.headers, body)
        except Exception as error:
            entry["error_type"] = type(error).__name__
            raise
        finally:
            entry["ms"] = round((time.monotonic() - start) * 1000)
            self.requests.append(entry)

    @staticmethod
    def origin(url):
        p = urllib.parse.urlsplit(url)
        return p.scheme, p.hostname, p.port or (443 if p.scheme == "https" else 80)

    def record(self, name, operation, diagnostic=False):
        start = time.monotonic()
        count = len(self.requests)
        result = {"name": name}
        try:
            result.update(status="PASS", evidence=operation() or {})
        except Exception as error:
            # Do not expose response bodies, request headers, passwords or cookies.
            detail = str(error) if isinstance(error, AssertionError) else type(error).__name__
            result.update(status="WARN" if diagnostic else "FAIL", detail=detail)
        result["requests"] = self.requests[count:]
        result["ms"] = round((time.monotonic() - start) * 1000)
        self.results.append(result)
        print(f"[{result['status']}] {name}")
        return result["status"] == "PASS"

    def skip(self, name, reason):
        self.results.append({"name": name, "status": "SKIP", "detail": reason})
        print(f"[SKIP] {name}: {reason}")

    def expect(self, method, path, code, data=None, headers=None):
        r = self.request(method, self.url(path), data, headers)
        require(r.code == code, f"Expected HTTP {code}, got {r.code}")
        return r

    def address(self, url, kind, source, followable):
        item = {"url": url, "kind": kind, "source": source, "followable": followable}
        if item not in self.addresses:
            self.addresses.append(item)

    def login(self, password):
        form = self.expect("GET", "/login", 200)
        require(form.headers.get("Referrer-Policy") == "same-origin", "Login form has incorrect referrer policy")
        require(form.headers.get("Cache-Control") == "no-store", "Login form must not be cached")
        data = urllib.parse.urlencode({"password": password}).encode()
        r = self.expect("POST", "/login", 303, data, {"Content-Type": "application/x-www-form-urlencoded"})
        require(r.headers.get("Location") == "/", "Login did not redirect to homepage")
        require(any(c.name == "lab_session" for c in self.cookies), "Session cookie missing")
        home = self.expect("GET", "/", 200)
        require(b"Resolve a product" in home.body, "Expected laboratory UI missing")
        return {"login": "accepted", "homepage": 200}

    def catalogue(self):
        info = self.expect("GET", "/lab/info", 200).json()
        require(info["public_origin"] == self.base, "Advertised public origin differs from configured base URL")
        require(info["dataset"] == "lab.test:dataset", "Unexpected synthetic dataset")
        entries = {f["name"]: f for f in info["fixtures"]}
        require(len(info["fixtures"]) == len(self.expected) and set(entries) == set(self.expected),
                "Fixture catalogue differs from this lab's expected four files")
        for name, content in self.expected.items():
            f = entries[name]
            require(f["did"] == "lab.test:" + name, "Unexpected DID")
            require(f["bytes"] == len(content) and f["sha256"] == digest(content),
                    f"Independent fixture oracle disagrees with manifest: {name}")
        safe_info = {k: info[k] for k in ("mode", "datalink_commit", "streamer_commit", "fixtures", "dataset", "public_origin")}
        self.save_json("manifest.json", safe_info)
        return safe_info

    def resolve(self, did):
        path = "/datalink/v1/links?" + urllib.parse.urlencode({"id": did})
        r = self.expect("GET", path, 200)
        require(b"<!DOCTYPE" not in r.body.upper() and b"<!ENTITY" not in r.body.upper(), "Unsafe XML declaration")
        root = ET.fromstring(r.body)
        require(root.tag == "{" + NS["v"] + "}VOTABLE", "Response is not a VOTable")
        descriptor = root.find('.//v:RESOURCE[@ID="product-streamer"]', NS)
        require(descriptor is not None, "Missing product-streamer service descriptor")
        params = descriptor.findall('v:PARAM[@name="accessURL"]', NS)
        require(len(params) == 1, "Expected exactly one Streamer accessURL")
        endpoint = params[0].get("value", "")
        approved = endpoint == self.url("/streamer/v1/data/product")
        self.address(endpoint, "Streamer accessURL", did, approved)
        require(approved, "Discovered Streamer endpoint outside approved lab route; not followed")
        direct_urls = []
        for table in root.findall(".//v:TABLE", NS):
            fields = [f.get("name") for f in table.findall("v:FIELD", NS)]
            if "access_url" not in fields:
                continue
            idx = fields.index("access_url")
            for row in table.findall(".//v:TR", NS):
                cells = row.findall("v:TD", NS)
                if len(cells) <= idx or not cells[idx].text:
                    continue
                url = cells[idx].text.strip()
                permitted = url in {self.url("/fixtures/lab.test/" + n) for n in self.expected}
                self.address(url, "DataLink row access_url", did, permitted)
                require(permitted, "Unapproved DataLink row URL; not followed")
                direct_urls.append(url)
        findings = {"did": did, "mime": r.headers.get("Content-Type", ""),
                    "standard_id": [x.get("value") for x in root.findall('.//v:INFO[@name="standardID"]', NS)]}
        self.standard_findings.append(findings)
        self.xmls[did], self.endpoints[did] = r.body, endpoint
        name = did.split(":", 1)[1]
        (self.directory / "votables" / (name + ".xml")).write_bytes(r.body)
        for url in direct_urls:
            file_name = urllib.parse.urlsplit(url).path.rsplit("/", 1)[-1]
            direct = self.request("GET", url)
            self.verify_file(direct, file_name)
            (self.directory / "direct" / file_name).write_bytes(direct.body)
        return {"did": did, "streamer": endpoint, "verified_direct_urls": direct_urls, **findings}

    def stream(self, did, token=TOKEN, range_header=None):
        headers = {"Content-Type": "application/xml"}
        if token:
            headers["Authorization"] = "Bearer " + token
        if range_header:
            headers["Range"] = range_header
        return self.request("POST", self.endpoints[did], self.xmls[did], headers)

    def verify_file(self, r, name):
        require(r.code == 200, f"Download {name}: expected 200, got {r.code}")
        expected = self.expected[name]
        require(len(r.body) == len(expected), f"Size mismatch: {name}")
        require(digest(r.body) == digest(expected), f"SHA-256 mismatch: {name}")
        if r.headers.get("Content-Length"):
            require(int(r.headers["Content-Length"]) == len(r.body), "Content-Length mismatch")
        return {"file": name, "bytes": len(r.body), "sha256": digest(r.body)}

    def download(self, name):
        r = self.stream("lab.test:" + name)
        evidence = self.verify_file(r, name)
        (self.directory / "downloads" / name).write_bytes(r.body)
        return evidence

    def archive(self):
        r = self.stream("lab.test:dataset")
        require(r.code == 200, f"TAR download: expected 200, got {r.code}")
        require("tar" in r.headers.get("Content-Type", ""), "Expected TAR content type")
        if r.headers.get("Content-Length"):
            require(int(r.headers["Content-Length"]) == len(r.body), "TAR Content-Length mismatch")
        members = []
        with tarfile.open(fileobj=io.BytesIO(r.body), mode="r:*") as archive:
            items = archive.getmembers()
            require(len(items) == 3 and {m.name for m in items} == {"image.fits", "readme.txt", "metadata.json"},
                    "Unexpected TAR members")
            for item in items:
                require(item.isfile() and item.size == len(self.expected[item.name]), "Unsafe TAR member or size")
                content = archive.extractfile(item).read(item.size + 1)
                require(content == self.expected[item.name], "TAR member content mismatch")
                members.append({"file": item.name, "bytes": len(content), "sha256": digest(content)})
        (self.directory / "downloads/dataset.tar").write_bytes(r.body)
        return {"bytes": len(r.body), "sha256": digest(r.body), "members": members}

    def partial(self):
        r = self.stream("lab.test:range.bin", range_header="bytes=0-99")
        require(r.code == 206, f"Range expected 206, got {r.code}")
        require(r.headers.get("Content-Range") == "bytes 0-99/1048576", "Incorrect Content-Range")
        require(r.body == self.expected["range.bin"][:100], "Partial bytes mismatch")
        (self.directory / "downloads/range.bin.partial").write_bytes(r.body)
        return {"bytes": len(r.body), "content_range": r.headers.get("Content-Range"), "sha256": digest(r.body)}

    def authentication(self, token, expected):
        r = self.stream("lab.test:image.fits", token=token)
        require(r.code == expected, f"Expected HTTP {expected}, got {r.code}")
        if token is None:
            self.challenge = r
        return {"http": r.code}

    def auth_discovery(self):
        r = self.challenge
        challenge = r.headers.get("WWW-Authenticate", "")
        body = r.body.decode("utf-8", "replace")
        try:
            detail = r.json().get("detail", "")
            body = detail if isinstance(detail, str) else body
        except (ValueError, AttributeError):
            pass
        advertised = re.findall(r'discovery_url="([^"\s]+)"', challenge + " " + body)
        for url in set(advertised):
            self.address(url, "Authentication discovery (not followed)", "Anonymous Streamer response", False)
        issues = []
        if not challenge:
            issues.append("Public response has no WWW-Authenticate header")
        if not advertised:
            issues.append("No authentication discovery URL advertised")
        elif not all(self.origin(u) == self.origin(self.base) for u in advertised):
            issues.append("Authentication discovery advertises another origin/localhost; not usable by external clients")
        require(not issues, "; ".join(issues))
        return {"advertised": advertised, "note": "Mock IAM is intentionally not publicly exposed or followed"}

    def server_suite(self):
        r = self.expect("POST", "/lab/run", 200)
        report = r.json()
        run_id = str(uuid.UUID(report["run_id"]))
        url = self.url("/lab/reports/" + run_id + ".json")
        self.address(url, "Internal-suite report", "/lab/run", True)
        downloaded = self.request("GET", url)
        require(downloaded.code == 200 and downloaded.json() == report, "Exported report differs from run result")
        self.save_json("internal-suite.json", report)
        failures = [x for x in report["results"] if x["status"] != "PASS"]
        unexpected = [x["name"] for x in failures if x["name"] != "DataLink standards baseline (diagnostic)"]
        require(not unexpected, "Internal service regressions: " + ", ".join(unexpected))
        return {"passed": report["passed"], "total": report["total"], "failures_preserved": failures,
                "note": "This check tests report retrieval and absence of new functional failures; not full conformance"}

    def save_json(self, name, content):
        (self.directory / name).write_text(json.dumps(content, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def run(self, password, internal_suite):
        for path in ["/", "/login", "/lab/info", "/lab/status", "/datalink/v1/links",
                     "/datalink/v1/ping", "/datalink/v1/health", "/streamer/v1/ping", "/streamer/v1/health"]:
            self.address(self.url(path), "Configured entry point (not auto-discovered)", "Lab API contract", True)
        if internal_suite:
            self.address(self.url("/lab/run"), "Configured test-run endpoint", "Lab API contract", True)
        self.record("Anonymous homepage redirects", lambda: self.expect("GET", "/", 303) and {"http": 303})
        self.record("Anonymous metadata denied", lambda: self.expect("GET", "/lab/info", 401) and {"http": 401})
        if not self.record("Login with same-origin form and open homepage", lambda: self.login(password)):
            self.skip("Discovery and downloads", "Login failed; check the laboratory password and base URL")
            return
        self.record("Reject null-origin login", lambda: self.expect("POST", "/login", 403, b"", {"Origin": "null"}) and {"http": 403})
        self.record("Reject foreign-origin login", lambda: self.expect("POST", "/login", 403, b"", {"Origin": "https://example.invalid"}) and {"http": 403})
        self.record("Reject cross-site login", lambda: self.expect("POST", "/login", 403, b"", {"Sec-Fetch-Site": "cross-site"}) and {"http": 403})
        self.record("Catalogue and independent fixture hashes", self.catalogue)
        self.record("Aggregated service status", self.health)
        for service in ["datalink", "streamer"]:
            for name in ["ping", "health"]:
                path = f"/{service}/v1/{name}"
                self.record(f"Public endpoint {path}", lambda p=path: self.expect("GET", p, 200) and {"http": 200})
        for name in [*self.expected, "dataset"]:
            did = "lab.test:" + name
            ok = self.record(f"Discover {did} and verify advertised direct URLs", lambda d=did: self.resolve(d))
            if ok:
                self.record(f"Streamer download and integrity: {name}", self.archive if name == "dataset" else lambda n=name: self.download(n))
            else:
                self.skip(f"Download {name}", "DID discovery failed")
        if "lab.test:range.bin" in self.endpoints:
            self.record("Range download: exact 100 bytes", self.partial)
            self.record("Out-of-bounds Range rejected", self.invalid_range)
        else:
            self.skip("Range checks", "range.bin discovery failed")
        if "lab.test:image.fits" in self.endpoints:
            for label, token, code in [("Missing access token", None, 401), ("Denied identity", "lab-denied-token", 403),
                                       ("Wrong token audience", "lab-raw-token", 401)]:
                self.record(label, lambda t=token, c=code: self.authentication(t, c))
            if hasattr(self, "challenge"):
                self.record("Authentication discovery usability", self.auth_discovery, diagnostic=True)
        else:
            self.skip("Service identity checks", "image.fits discovery failed")
        self.record("Malformed XML rejected", lambda: self.expect("POST", "/streamer/v1/data/product", 400, b"<broken>",
                    {"Content-Type": "application/xml", "Authorization": "Bearer " + TOKEN}) and {"http": 400})
        self.record("Mock token endpoint not publicly exposed", lambda: self.expect("POST", "/mock/token", 404, b"") and {"http": 404})
        if self.standard_findings:
            self.save_json("standards-findings.json", self.standard_findings)
            self.record("DataLink MIME diagnostic", self.mime_check, diagnostic=True)
            self.record("DataLink standardID INFO diagnostic", self.standard_id_check, diagnostic=True)
        if internal_suite:
            self.record("Run internal suite and verify exported report", self.server_suite)

    def health(self):
        statuses = self.expect("GET", "/lab/status", 200).json()
        require({x["service"] for x in statuses} == {"DataLink", "Streamer"}, "Missing service status")
        require(all(x["http"] == 200 for x in statuses), "An upstream service is unhealthy")
        return {"services": statuses}

    def invalid_range(self):
        r = self.stream("lab.test:range.bin", range_header="bytes=2000000-2000010")
        require(r.code == 416, f"Expected 416, got {r.code}")
        return {"http": 416}

    def mime_check(self):
        require(all("application/x-votable+xml" in f["mime"] for f in self.standard_findings),
                "DataLink MIME differs from application/x-votable+xml; inspect standards-findings.json")

    def standard_id_check(self):
        require(all(f["standard_id"] for f in self.standard_findings), "DataLink standardID INFO is missing")

    def finish(self):
        counts = dict(Counter(r["status"] for r in self.results))
        report = {"timestamp": datetime.now(timezone.utc).isoformat(), "base_url": self.base,
                  "scope": "Public lab HTTP chain; real service processes with simulated IAM/DMAPI/PAPI/discovery",
                  "limitations": ["Not real SRCNet/OIDC integration, load testing or complete IVOA conformance",
                                  "Discovery follows only approved same-origin lab data routes; never follows mock IAM URLs",
                                  "Bootstrap addresses are configured, not SCAPI-discovered",
                                  "HTTP is unencrypted; use only this disposable lab password"],
                  "summary": counts, "results": self.results, "addresses": self.addresses,
                  "requests": self.requests}
        self.save_json("report.json", report)
        self.save_json("addresses.json", self.addresses)
        lines = ["# DataLink / Streamer public end-to-end test", "", f"Time: {report['timestamp']}",
                 f"Base URL: {self.base}", "", "Summary: " + ", ".join(f"{k}={v}" for k, v in counts.items()),
                 "", "## Checks", "", "| Result | Check | Evidence / issue |", "|---|---|---|"]
        for r in self.results:
            detail = r.get("detail") or json.dumps(r.get("evidence", {}), ensure_ascii=False)
            lines.append("| " + " | ".join(str(x).replace("|", "\\|").replace("\n", " ") for x in [r["status"], r["name"], detail]) + " |")
        lines += ["", "## Address inventory", "", "| Type | Address | Source | Followable |", "|---|---|---|---|"]
        for a in self.addresses:
            lines.append(f"| {a['kind']} | {a['url']} | {a['source']} | {a['followable']} |")
        lines += ["", "## Scope and limitations", ""] + ["- " + x for x in report["limitations"]]
        (self.directory / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("Summary: " + json.dumps(counts))
        print("Report: " + str(self.directory / "report.md"))
        return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE)
    parser.add_argument("--password-file", type=Path, help="Existing lab credentials file (Password: ...) or a one-line password file")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent / "evidence/public-e2e")
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--skip-server-suite", action="store_true", help="Skip optional internal-server suite/report export")
    parser.add_argument("--strict", action="store_true", help="Exit 2 for diagnostic WARNs even if functional tests pass")
    args = parser.parse_args()
    require(args.timeout > 0, "Timeout must be positive")
    if args.password_file:
        raw = args.password_file.read_text(encoding="utf-8").strip()
        values = [line[len("Password: "):] for line in raw.splitlines() if line.startswith("Password: ")]
        require(len(values) == 1 or (not values and len(raw.splitlines()) == 1), "Unrecognized password file format")
        password = values[0] if values else raw
    else:
        password = getpass.getpass("Laboratory password (not an SKA password): ")
    require(bool(password), "Empty laboratory password")
    run_name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    directory = args.output.resolve() / run_name
    lab = LabTest(args.base_url, directory, args.timeout)
    directory.mkdir(parents=True, exist_ok=False)
    for name in ["votables", "downloads", "direct"]:
        (directory / name).mkdir()
    try:
        lab.run(password, not args.skip_server_suite)
    except Exception as error:
        lab.results.append({"name": "Test runner", "status": "FAIL", "detail": type(error).__name__})
    finally:
        counts = lab.finish()
    return 1 if counts.get("FAIL") or counts.get("SKIP") else (2 if args.strict and counts.get("WARN") else 0)


if __name__ == "__main__":
    sys.exit(main())
