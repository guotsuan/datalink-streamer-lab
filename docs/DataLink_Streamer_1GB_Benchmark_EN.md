# DataLink and Product Streamer: 1 GB Download Benchmark

**Test date:** 5 October 2026 | **Download start:** 08:10:54 UTC (16:10:54 China time)
**Endpoint:** http://64.176.188.89:18080 | **Product:** `lab.test:large-1tb.fits`

## Test configuration

The Python client first measured a 10-second, single-stream reverse TCP iperf3 baseline from the temporary VM to the client. It then resolved the synthetic product through DataLink and downloaded the first 1 GB (1,000,000,000 bytes) through Product Streamer, with no total download time limit. The source was a sparse, zero-filled FITS file with approximately 1 TB of logical data. Received blocks were checked and discarded rather than saved to local disk.

## Results

| Measurement | Result |
|---|---:|
| iperf3 receiver throughput | 22.327 Mbps / 2.662 MiB/s |
| iperf3 duration / received bytes | 10.003 seconds / 27,918,336 bytes |
| Streamer download size | 1,000,000,000 bytes (1 GB) |
| Download duration | 301.038 seconds (5 min 1 sec) |
| Download average throughput | 26.575 Mbps / 3.168 MiB/s |
| Time to first byte | 0.608 seconds |
| Download / iperf3 throughput | 119.03% |
| Transfer completion / sample content check | PASS / PASS |

## Data integrity verification

The client checked the HTTP status, Content-Length, Content-Range and absence of compression, and confirmed that all 1,000,000,000 requested bytes were received. It checked the FITS header's SIMPLE and END markers and verified that every received byte after the 2,880-byte header was zero, matching this synthetic fixture's expected payload. These checks passed for the complete 1 GB sample.

SHA-256 was not computed or compared with an independent reference digest. The header check was limited to these markers, rather than full FITS validation. The test therefore provides byte-count and synthetic-content verification for the downloaded sample, but not a checksum verification of the entire 1 TB source file. A subsequent integrity test should compute a streaming SHA-256 and compare it with a separately prepared digest for the exact requested range.

## Assessment

The 1 GB sample completed successfully at an average 26.575 Mbps. Its throughput exceeded the preceding iperf3 measurement; this is possible because the tests ran sequentially for different durations and used different ports, with changing network conditions and TCP startup effects. This single comparison does not establish a maximum network rate or identify a Streamer bottleneck. Repeat paired measurements to assess variability. Results describe this temporary VM-to-client path; a complete 1 TB transfer and CNSRC-node performance were not tested.

**Evidence:** User-supplied JSON result; no additional transfer was performed to prepare this report.
