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
No real SCAPI/Rucio/StoRM integration, full schema validation, load benchmark,
large-file test, interrupted/resumed transfer or dependency-recovery acceptance
is claimed. The partial-byte check uses a Streamer POST; RFC 9110 specifies Range
handling for GET, so this is product behavior rather than general Range conformance.

## Repository preparation checks

On 22 September 2026, the exported external client passed **9 offline unit tests**.
The isolated gateway regression script also passed **13 checks**, using a local
test environment with FastAPI 0.141.1 and HTTPX 0.28.1; no live server calls were made.
The environment helper passed a dry run; it did not install or start services.
These checks are separate from the recorded 21 September live results. A fresh
end-to-end deployment from this repository has not been verified.
