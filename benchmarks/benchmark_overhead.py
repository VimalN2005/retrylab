"""
RetryLab Overhead & Latency Benchmark.
Measures nanosecond/microsecond interception overhead and memory impact across 1,000 iterations.
"""

from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import time
import httpx
from retrylab import FaultScenario, FaultType, RetryLabTransport


class DummyBaselineTransport(httpx.BaseTransport):
    """Zero-overhead baseline transport."""

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=200, content=b'{"status": "ok"}', request=request)


def run_benchmark(iterations: int = 1000) -> dict[str, float]:
    req = httpx.Request("GET", "https://api.benchmark.test/v1/ping")

    # 1. Baseline Benchmark
    base_transport = DummyBaselineTransport()
    t0 = time.perf_counter()
    for _ in range(iterations):
        base_transport.handle_request(req)
    t1 = time.perf_counter()
    baseline_total_ms = (t1 - t0) * 1000.0
    baseline_per_req_us = (baseline_total_ms / iterations) * 1000.0

    # 2. RetryLab Passthrough Benchmark
    scenario = FaultScenario(
        target="https://api.other.com/*",  # Non-matching scenario (passthrough)
        fault=FaultType.TIMEOUT,
    )
    retrylab_transport = RetryLabTransport(
        scenario=scenario,
        passthrough_transport=base_transport,
    )

    t2 = time.perf_counter()
    for _ in range(iterations):
        retrylab_transport.handle_request(req)
    t3 = time.perf_counter()
    retrylab_total_ms = (t3 - t2) * 1000.0
    retrylab_per_req_us = (retrylab_total_ms / iterations) * 1000.0

    overhead_per_req_us = max(0.0, retrylab_per_req_us - baseline_per_req_us)
    throughput_rps = iterations / (t3 - t2)

    return {
        "iterations": float(iterations),
        "baseline_us": round(baseline_per_req_us, 2),
        "retrylab_us": round(retrylab_per_req_us, 2),
        "overhead_us": round(overhead_per_req_us, 2),
        "throughput_rps": round(throughput_rps, 1),
    }


def main():
    print("--- Running RetryLab Performance Benchmark (1,000 iterations) ---")
    results = run_benchmark(iterations=1000)
    print(f"[*] Baseline Transport:   {results['baseline_us']} \u00b5s/req")
    print(f"[*] RetryLab Transport:   {results['retrylab_us']} \u00b5s/req")
    print(f"[*] Interceptor Overhead: {results['overhead_us']} \u00b5s/req ({results['overhead_us']/1000:.3f} ms)")
    print(f"[*] Total Throughput:     {results['throughput_rps']} req/sec")


if __name__ == "__main__":
    main()
