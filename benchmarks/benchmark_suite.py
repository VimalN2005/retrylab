"""
Comprehensive Polyglot Benchmark Suite for RetryLab.
Measures latency percentiles (P50, P90, P95, P99), throughput (RPS), and memory footprint.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure repository root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from retrylab.benchmark import (
    BenchmarkReport,
    DummyBaselineTransport,
    LatencyMetrics,
    PythonBenchmarkRunner,
    compute_percentiles,
    run_go_benchmark,
    run_polyglot_benchmark,
    run_ts_benchmark,
)

__all__ = [
    "BenchmarkReport",
    "DummyBaselineTransport",
    "LatencyMetrics",
    "PythonBenchmarkRunner",
    "compute_percentiles",
    "run_go_benchmark",
    "run_polyglot_benchmark",
    "run_ts_benchmark",
]


if __name__ == "__main__":
    runner = PythonBenchmarkRunner(iterations=1000)
    rep = runner.run_all()
    print(f"--- RetryLab Python Benchmark ({rep.iterations} iterations) ---")
    for name, bench in rep.benchmarks.items():
        print(f"[{name}]")
        print(f"  Mean: {bench.mean_us} µs | P50: {bench.p50_us} µs | P99: {bench.p99_us} µs")
        print(f"  Throughput: {bench.throughput_rps} req/s | Overhead: {bench.overhead_us} µs | Peak Mem: {bench.memory_peak_kb} KB")
