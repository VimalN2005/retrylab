# 🏎️ RetryLab Performance & Latency Benchmark Results

Measured on 1,000 continuous request/response cycles using `benchmarks/benchmark_overhead.py`:

| Component | Average Latency | Throughput | Overhead |
| :--- | :---: | :---: | :---: |
| **Raw Baseline HTTPX Transport** | `13.98 µs` | 71,500 req/sec | Baseline (0.0 µs) |
| **RetryLab Interceptor Transport** | `58.67 µs` | **17,044 req/sec** | **+0.045 ms** (+44.6 µs) |

### Key Takeaways:
- **Sub-Millisecond Overhead:** RetryLab adds less than `0.05ms` per intercepted request.
- **Zero Daemon Penalty:** Because interception happens directly in-process at the transport layer, there is zero socket hopping or external proxy latency penalty.
- **CI Throughput:** Capable of processing over 17,000 requests per second in local testing suites.
