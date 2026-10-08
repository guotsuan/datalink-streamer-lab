# DataLink & Product Streamer
## Software Verification Report

Technical briefing | Quan Guo | Updated 22 September 2026

### 1. Software and Versions

**Objective.** Verify the software path from a synthetic data identifier (DID), through DataLink discovery, to Product Streamer delivery and independent file-integrity checks. The laboratory uses official SKA service code with simulated supporting services.

| Component | Software, version and role |
|---|---|
| DataLink | Official [ska-src-dm-datalink](https://gitlab.com/ska-telescope/src/src-dm/ska-src-dm-datalink), **0.1.5**. Resolves DIDs and returns VOTable links and service descriptors. Commit: `997dfb03944b9c44283411264ca1c07b48b03a8e`. |
| Product Streamer | Official [ska-src-dm-product-streamer-api](https://gitlab.com/ska-telescope/src/src-dm/ska-src-dm-product-streamer-api), **0.1.2**. Delivers single files and TAR datasets. Commit: `27df8cb247105faf67a6d278dd9819528f211dd3`. |
| Server environment | Recorded baseline: **Rocky Linux 10.2**, **Python 3.13.15**, three separate Python environments, systemd process supervision. |
| Service dependencies | Official services: **FastAPI 0.124.4**, **Uvicorn 0.34.3**. Portal: **FastAPI 0.141.1**, **Uvicorn 0.53.0**. HTTP client: **HTTPX 0.28.1**. Full dependency snapshots are included in the repository. |
| Laboratory integration | Custom Python portal, password gateway, process supervisor and deterministic fixture generator, with HTML/CSS/JavaScript UI. This code has no separate semantic release version; Git history identifies the published snapshot. |
| Python tests | Custom external client `test_public_e2e.py`: **Python 3.9+**, standard library only. Additional scripts cover the internal suite, gateway and client regressions. |

**Test environment.** [http://64.176.188.89:18080](http://64.176.188.89:18080). DataLink and Streamer run on server loopback ports 18081 and 18082 behind the laboratory gateway. The official application source is unmodified; configuration directs dependencies to local fixtures.

**Simulation boundary.** DMAPI, IAM, PAPI and colocated-service discovery are simulated. No real SCAPI, Rucio, StoRM or federated SRCNet service is connected. Four deterministic files are used: FITS, text, JSON and a 1 MiB binary. The dataset contains the first three files. Public HTTP is unencrypted; use synthetic data and a disposable laboratory password only.

**Evaluation basis.** [IVOA DataLink 1.1](https://www.ivoa.net/documents/DataLink/20231215/REC-DataLink-1.1.html), [VOTable 1.4](https://www.ivoa.net/documents/VOTable/20191021/REC-VOTable-1.4-20191021.html), [HTTP Semantics / RFC 9110](https://www.rfc-editor.org/rfc/rfc9110.html) and [SHA-256 / FIPS 180-4](https://csrc.nist.gov/pubs/fips/180-4/upd1/final). These guide selected checks; they do not establish full standards conformance.

<!-- PAGEBREAK -->

### 2. Test Coverage and Reproducible Code

| Test group | Checks and purpose |
|---|---|
| Access and health | Check login, origin restrictions, and DataLink/Streamer ping and health endpoints to establish protected access and service availability. |
| DID and address discovery | Resolve four file DIDs and one dataset DID; parse VOTables and verify advertised direct-file and Streamer URLs. Bootstrap addresses are configured, not SCAPI-discovered. |
| File and dataset delivery | Download four files through direct links and Streamer; compare byte counts and independently generated SHA-256 values. Inspect all three TAR members without extracting them to disk. |
| Partial data and errors | Verify exact 100-byte retrieval and HTTP 416 rejection; test missing-token, denied and wrong-audience synthetic identities, malformed XML, and blocked mock-token access. |
| Diagnostics and evidence | Inspect MIME, standardID and authentication discovery; retain address provenance, responses, downloaded fixtures and machine-readable results. |

**Public GitHub repository:** [github.com/guotsuan/datalink-streamer-lab](https://github.com/guotsuan/datalink-streamer-lab).

The repository includes server integration code, systemd examples, dependency snapshots, Python tests and an English [README.md](https://github.com/guotsuan/datalink-streamer-lab/blob/main/README.md). [Deployment instructions](https://github.com/guotsuan/datalink-streamer-lab/blob/main/docs/DEPLOYMENT.md) distinguish the original VM configuration from fresh setup. Run the [external test script](https://github.com/guotsuan/datalink-streamer-lab/blob/main/lab/test_public_e2e.py) with `python3 lab/test_public_e2e.py`; enter the disposable password when prompted. Passwords, signing keys and local runtime evidence are excluded from the repository.

### 3. Test Results

**Latest supplied external run: 22 September 2026, 15:05:15 UTC.** A total of **41 HTTP requests** produced **33 checks: 30 PASS / 3 WARN / 0 FAIL**. The internal suite exported by this run returned **14/15**, with one MIME diagnostic failure overlapping an external warning. These counts match the 21 September baseline; requests, checks and suites have different denominators.

**Verified outcome.** DID-to-link resolution, four-file delivery, three-member TAR integrity, exact partial bytes and the tested negative responses worked with simulated dependencies. Latest evidence run: `20260922T150508Z-661cd650`. Pages 3-6 contain supplied screenshots, all 33 check results, file hashes and an address inventory. The full original `report.md` is embedded as a PDF attachment.

**Recorded observations.** Three diagnostic warnings remain: DataLink returns `application/xml`; DataLink standardID INFO is absent; and the public unauthorized response omits WWW-Authenticate and advertises a localhost mock discovery URL. These observations are retained, not relabelled as passes.

**Conclusion.** The tests establish a repeatable synthetic software-verification baseline, not production readiness or full IVOA certification. Real discovery/authentication, interrupted-transfer recovery, large-file/concurrency tests and failure recovery remain unverified. Partial-download testing uses Streamer POST, not standard HTTP GET-range conformance. This revision incorporates the user's new evidence; no additional live tests were executed during report preparation.
