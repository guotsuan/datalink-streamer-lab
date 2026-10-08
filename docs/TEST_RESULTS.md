# Recorded software verification results

## External run

- Test time: **21 September 2026, 05:11 UTC**.
- Evidence identifier: `20260921T051110Z-bae7b261`.
- Endpoint: `http://64.176.188.89:18080`.
- **41 HTTP requests; 33 checks; 30 PASS / 3 WARN / 0 FAIL.**
- Separate internal suite: **14/15**. Its MIME diagnostic failure overlaps the external MIME warning.
- Raw evidence is retained by the owner, not published here. This is a summary, not an independent re-test.

## Functional coverage

| Group | Recorded evidence |
|---|---|
| Access | Anonymous home redirects; anonymous metadata denied; same-origin login works; null/foreign/cross-site login rejected |
| Service health | Aggregate status plus DataLink and Streamer ping/health |
| Discovery | Four file DIDs and one dataset DID; advertised direct links and Streamer descriptors |
| Delivery | Four direct-file downloads and four Streamer downloads checked against independent fixture bytes and SHA-256 |
| TAR | Three members: `image.fits`, `readme.txt`, `metadata.json`; sizes and hashes checked without extraction |
| Partial bytes | Exact `bytes=0-99` result; Content-Range `bytes 0-99/1048576`; out-of-bounds Range rejected with 416 |
| Negative responses | Missing token 401; denied synthetic identity 403; simulated wrong audience 401; malformed XML 400; public mock token route 404 |
| Evidence export | Internal-suite report retrieved, with its diagnostic failure preserved |

## Diagnostic observations

1. DataLink response MIME is `application/xml`. The test expects the more specific
   DataLink VOTable media type. Its current preference for `application/x-votable+xml`
   is narrower than DataLink's allowance of `text/xml`; review the diagnostic against
   the agreed standard version before treating it as full compliance validation.
2. DataLink `standardID` INFO is absent in the returned VOTable.
3. The public unauthorized response has no `WWW-Authenticate` header and advertises
   a localhost mock discovery URL unusable by external clients. The client does not
   follow it or send credentials to another origin.

## Interpretation and remaining scope

This is a working synthetic DID-to-byte delivery baseline. Official DataLink and
Streamer processes are real; IAM, DMAPI, PAPI and colocated-service discovery are
mocked. Synthetic audience/permission checks are not real JWT verification.
No real SCAPI/Rucio/StoRM integration, full schema validation, concurrency/load,
interrupted/resumed transfer or dependency-recovery acceptance
is claimed. The partial-byte check uses a Streamer POST; RFC 9110 specifies Range
handling for GET, so this is product behavior rather than general Range conformance.

## Repository preparation checks

On 22 September 2026, the exported external client passed **9 offline unit tests**.
The isolated gateway regression script also passed **13 checks**, using a local
test environment with FastAPI 0.141.1 and HTTPX 0.28.1; no live server calls were made.
The environment helper passed a dry run; it did not install or start services.
These checks are separate from the recorded 21 September live results. A fresh
end-to-end deployment from this repository has not been verified.

## October large-range benchmark

The 5 October 2026 test transferred exactly **10,000,000,000 bytes** from the
approximately 1 TB sparse FITS via DataLink and Product Streamer. A 10-second
reverse single-stream iperf3 baseline ran immediately before the HTTP download.

| Measurement | Recorded result |
|---|---:|
| iperf3 receiver throughput | 137.746 Mbps |
| HTTP download throughput | 138.757 Mbps / 16.541 MiB/s |
| Download time | 576.548 s |
| Received / requested bytes | 10,000,000,000 / 10,000,000,000 |
| Download / iperf3 throughput | 100.73% |
| SHA-256 compared with independent source-range read | PASS |
| Synthetic header / zero-data check | PASS |

Digest: `84b841e5ef821e36864a1c02573d509d879aeea3d9c32ed06b69faddc391e032`.
The source digest was computed over SSH before the network tests; the received
digest was computed incrementally during download. Bytes were discarded after
checking. The published [JSON evidence](evidence/10GB_SHA256_20261005.json)
retains measurements while omitting the client hostname, addresses and iperf
session identifier. Full original evidence remains with the owner.

[PDF report](DataLink_Streamer_10GB_SHA256_Report_EN.pdf) and
[Markdown report](DataLink_Streamer_10GB_SHA256_Report_EN.md).
This covers the complete **10 GB range**, not a full 1 TB transfer, physical disk
I/O or CNSRC-node performance. Sequential tests differ in duration and may
encounter varying network conditions or port policies.

## Publication checks, 8 October 2026

The export passed 9 external-client unit tests, 3 sparse-fixture tests and 5
streaming/checksum tests (including rejection of a reference-hash mismatch).
The browser benchmark harness passed 3 scenarios: bounded sample, incorrect
length and declined full-transfer confirmation. The isolated login gateway
regression passed 13 checks with FastAPI 0.141.1 and HTTPX 0.28.1. JavaScript syntax checks and
the environment-preparation dry run passed. These are publication regression
checks; the recorded 10 GB download was not repeated for this update.
