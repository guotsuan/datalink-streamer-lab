"""Small, read-only suite against the actual upstream service processes."""
import asyncio
import hashlib
import io
import json
import tarfile
import time
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
import httpx
from fixtures import STORAGE, SCOPE, contents, DL_COMMIT, PS_COMMIT, public_base

NS = {"v": "http://www.ivoa.net/xml/VOTable/v1.3"}


async def run():
    results = []
    async with httpx.AsyncClient(timeout=25, trust_env=False) as c:
        async def record(name, operation, check):
            start = time.monotonic()
            try:
                response = await operation()
                detail = check(response)
                results.append({"name": name, "status": "PASS", "http": response.status_code,
                                "detail": detail, "ms": round((time.monotonic() - start) * 1000)})
                return response
            except Exception as e:
                results.append({"name": name, "status": "FAIL", "detail": str(e)[:500],
                                "ms": round((time.monotonic() - start) * 1000)})
                return None

        def expected(code):
            def check(r):
                assert r.status_code == code, f"Expected HTTP {code}, received {r.status_code}: {r.text[:250]}"
                return f"HTTP {code}"
            return check

        dl, ps = "http://127.0.0.1:18081", "http://127.0.0.1:18082"
        for name, base in [("DataLink", dl), ("Streamer", ps)]:
            for path in ("ping", "health"):
                await record(f"{name} {path}", lambda b=base, p=path: c.get(b + "/v1/" + p), expected(200))

        def votable(r):
            expected(200)(r)
            root = ET.fromstring(r.content)
            descriptor = root.find('.//v:RESOURCE[@ID="product-streamer"]/v:PARAM[@name="accessURL"]', NS)
            assert descriptor is not None, "Streamer descriptor absent"
            assert descriptor.get("value") == public_base() + "/streamer/v1/data/product"
            return "Parseable VOTable; Streamer accessURL discovered"

        single = await record("Resolve single-file DID", lambda: c.get(dl + "/v1/links", params={"id": SCOPE + ":image.fits"}), votable)
        dataset = await record("Resolve dataset DID", lambda: c.get(dl + "/v1/links", params={"id": SCOPE + ":dataset"}), votable)
        headers = {"Authorization": "Bearer lab-service-token", "Content-Type": "application/xml"}
        if single is not None:
            def checksum(r):
                expected(200)(r)
                assert r.content == contents()["image.fits"], "File content mismatch"
                assert int(r.headers["content-length"]) == len(r.content)
                return "SHA-256 " + hashlib.sha256(r.content).hexdigest()
            await record("VOTable → file bytes + SHA-256", lambda: c.post(ps + "/v1/data/product", content=single.content, headers=headers), checksum)
            await record("No token → 401", lambda: c.post(ps + "/v1/data/product", content=single.content, headers={"Content-Type": "application/xml"}), expected(401))
            await record("Denied fixture token → 403", lambda: c.post(ps + "/v1/data/product", content=single.content, headers={**headers, "Authorization": "Bearer lab-denied-token"}), expected(403))

        if dataset is not None:
            def archive(r):
                expected(200)(r)
                assert int(r.headers["content-length"]) == len(r.content)
                with tarfile.open(fileobj=io.BytesIO(r.content)) as archive:
                    expected_names = {"image.fits", "readme.txt", "metadata.json"}
                    assert len(archive.getmembers()) == 3 and set(archive.getnames()) == expected_names
                    for name in expected_names:
                        assert archive.extractfile(name).read() == contents()[name], f"Mismatch: {name}"
                return "3 TAR members; sizes and bytes match fixture manifest"
            await record("Dataset → TAR + member integrity", lambda: c.post(ps + "/v1/data/product", content=dataset.content, headers=headers), archive)

        product = [{"did": SCOPE + ":range.bin", "path": str(STORAGE / SCOPE / "range.bin")}]
        jheaders = {"Authorization": "Bearer lab-service-token"}
        def partial(r):
            expected(206)(r)
            assert r.content == contents()["range.bin"][:100]
            assert r.headers["content-range"] == "bytes 0-99/1048576"
            return "206; exact 100 bytes and Content-Range"
        await record("JSON request + Range 0–99", lambda: c.post(ps + "/v1/data/product", json=product, headers={**jheaders, "Range": "bytes=0-99"}), partial)
        await record("Unsatisfiable Range → 416", lambda: c.post(ps + "/v1/data/product", json=product, headers={**jheaders, "Range": "bytes=2000000-2000010"}), expected(416))
        missing = [{"did": SCOPE + ":absent", "path": str(STORAGE / SCOPE / "absent")}]
        await record("Missing file → 404", lambda: c.post(ps + "/v1/data/product", json=missing, headers=jheaders), expected(404))
        await record("Malformed XML → 400", lambda: c.post(ps + "/v1/data/product", content=b"<broken>", headers=headers), expected(400))
        # Check conformance separately; do not silently patch official responses.
        if single is not None:
            def standard(r):
                assert "application/x-votable+xml" in r.headers.get("content-type", ""), "Upstream returns application/xml, not DataLink MIME type"
                root = ET.fromstring(r.content)
                assert root.find('.//v:INFO[@name="standardID"]', NS) is not None, "DataLink standardID INFO missing"
                return "DataLink MIME and standardID present"
            await record("DataLink standards baseline (diagnostic)", lambda: c.get(dl + "/v1/links", params={"id": SCOPE + ":image.fits"}), standard)
    return {"run_id": str(uuid.uuid4()), "timestamp": datetime.now(timezone.utc).isoformat(),
            "mode": "official services, simulated DMAPI/PAPI/IAM", "datalink_commit": DL_COMMIT,
            "streamer_commit": PS_COMMIT, "results": results,
            "passed": sum(r["status"] == "PASS" for r in results), "total": len(results),
            "notes": ["Auth tests exercise official challenge handling against a simulated permission service.",
                      "Does not certify production readiness, load limits, full DataLink conformance or real SRCNet integration."]}


if __name__ == "__main__":
    print(json.dumps(asyncio.run(run()), indent=2))
