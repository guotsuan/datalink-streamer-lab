# DataLink and Product Streamer: 10 GB Download and SHA-256 Test

**Download start (UTC):** 2026-10-05T08:25:19.779012+00:00

**Endpoint:** http://64.176.188.89:18080 | **Product:** `lab.test:large-1tb.fits`

## Test configuration

A 10-second, single-stream reverse TCP iperf3 baseline was followed by a 10 GB download from the temporary VM to the client. DataLink resolved the synthetic product; Product Streamer delivered bytes 0-9999999999 from the approximately 1 TB sparse FITS source. The download had no total time limit. Blocks were hashed, checked and discarded. A reference SHA-256 was independently computed from the same byte range on the server before the network tests.

## Results

| Measurement | Result |
|---|---:|
| iperf3 receiver throughput | 137.746 Mbps / 16.421 MiB/s |
| iperf3 duration / received bytes | 10.003 s / 172,228,608 bytes |
| Requested / received download bytes | 10,000,000,000 / 10,000,000,000 |
| Download duration | 576.548 s (9.61 min) |
| Download average throughput | 138.757 Mbps / 16.541 MiB/s |
| Time to first byte | 1.287 s |
| Download / iperf3 throughput | 100.73% |
| Transfer completion | PASS |
| SHA-256 comparison | PASS |
| Synthetic header / zero-data check | PASS |

## Data integrity verification

The requested byte count and HTTP range were verified. The received SHA-256 matched the independently computed source-range digest; FITS header markers and zero-filled payload checks also passed. Verification covers the complete downloaded range.

**Received SHA-256:** `84b841e5ef821e36864a1c02573d509d879aeea3d9c32ed06b69faddc391e032`

**Reference SHA-256:** `84b841e5ef821e36864a1c02573d509d879aeea3d9c32ed06b69faddc391e032`

**Evidence:** [Reviewed JSON results](evidence/10GB_SHA256_20261005.json). Original run: `20261005T082429Z`.
