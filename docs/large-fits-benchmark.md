# Optional 1 TB sparse FITS benchmark

- DID: `lab.test:large-1tb.fits`.
- 1,000,000 x 1,000,000 unsigned 8-bit zero pixels: 1 decimal TB of pixel data, not 1 TiB.
- Total file size: **1,000,000,005,120 bytes**, including the FITS header and 2880-byte padding.
- Sparse file: only the header occupies disk blocks. Network transfers still carry zero bytes; compression is disabled between proxies and clients reject compressed responses.
- This measures the VM-to-client network and streaming stack, **not physical disk read performance** and not CNSRC-node performance.
- All authentication and discovery dependencies remain simulated. Existing small fixtures and their test suite are unchanged; the large file is opt-in and is not part of the three-file dataset.

## Website

Log in at http://64.176.188.89:18080/ and use **1 TB sparse FITS / 大文件下载测速** near the bottom. Default: at most 256 MiB or 30 seconds. An optional 1 GiB sample has a 120-second cap. Full transfer requires explicit confirmation and may incur public bandwidth charges. Stop cancels the active browser request. The browser discards received blocks without keeping the whole file in RAM or saving it to disk.

The displayed average includes discovery and connection setup. Sample throughput is not proof that a complete 1 TB transfer succeeded. No full-file checksum has been computed; header and sampled zero regions are checked separately during deployment.

## Python client

Download `download_large.py` from the authenticated page. Requires Python 3.9+, local iperf3 and SSH on macOS/Linux. The default workflow first runs a 10-second **reverse, single-stream TCP iperf3 baseline**, then downloads the sample through DataLink/Product Streamer. Both transfer from the same VM to the client; iperf traffic is direct, not carried through SSH. Password is prompted, not supplied on the command line.

SSH access to `gq@64.176.188.89` must already work without an interactive password; remote Python 3, iperf3 and `timeout` are required. On this VM, passwordless sudo permits a runtime firewalld rule for only the SSH client's IPv4 address and selected TCP port (default 5201). It expires after 60 seconds and is removed when the test ends. The one-off server is terminated too; no persistent service or permanent firewall rule is created. Other clients without SSH access may explicitly use `--skip-iperf` for download-only tests. A failed baseline stops the comparison rather than silently omitting it.

```sh
python3 download_large.py
python3 download_large.py --iperf-seconds 10 --report comparison.json
python3 download_large.py --mib 1024 --report speed.json
# 10 GB (decimal), SHA-256 checked against an independent server-side read:
python3 download_large.py --bytes 10000000000 --report comparison_10GB.json
# Explicit ~1 TB network transfer, discard on the client:
python3 download_large.py --full --confirm-1tb
# Save the full file (requires >1 TB of free local disk):
python3 download_large.py --full --confirm-1tb --output large-1tb.fits
```

No full 1 TB transfer has been run during deployment. Ctrl-C stops the client. Incomplete files are retained and must not be reported as successful FITS downloads. The client checks HTTP status, expected length/range and absence of compression. It computes SHA-256 while receiving blocks and compares it with an independent SSH read of exactly the same source-file range, prepared before iperf3. A mismatch fails the test. The optional `--expected-sha256` accepts an independently obtained reference and avoids the SSH hashing step. Hashing an entire 1 TB source may take substantial time. Resume is not implemented.

The Python client defaults to exactly **1 GB (1,000,000,000 bytes)** from the large file, with no total download time limit. A 10-second socket inactivity timeout still detects a stalled connection; it does not limit a progressing download. It streams and discards blocks, checks the sampled FITS header and zero-filled data, and optionally saves JSON measurements without passwords or cookies. Its average includes the Streamer request setup but excludes login and DataLink discovery. `--mib 1024` explicitly selects 1 GiB (1,073,741,824 bytes). The existing `lab/test_public_e2e.py` remains the small-fixture functional suite with its 16 MiB response safety limit; use this separate client for throughput testing.

The JSON includes iperf3's raw result, receiver throughput in Mbit/s and MiB/s, and `download_to_iperf_percent`. Sequential results can vary with TCP startup and network conditions; different ports may have different network policies. A low ratio alone does not prove a Streamer bottleneck, nor is a ratio over 100% inherently an error. iperf3 itself generates additional traffic for its configured duration; the `--mib` limit applies only to HTTP. Measurements apply to this temporary VM, not a CNSRC node.

## Provisioning

`python3 large_fixture.py` creates the sparse file exclusively under the laboratory fixture storage. Existing files are not overwritten. The server exposes its metadata separately at `/lab/large/info` to keep baseline manifests and small-file tests unchanged. Changes are limited to the lab integration, not the installed DataLink or Product Streamer packages.
