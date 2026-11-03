"""
Regression test for RetryLab interception overhead.
"""

from benchmarks.benchmark_overhead import run_benchmark


def test_interception_overhead_under_one_millisecond():
    results = run_benchmark(iterations=100)
    # Assert overhead per request is strictly less than 1.0 ms (1000 µs)
    assert results["overhead_us"] < 1000.0
    assert results["throughput_rps"] > 1000.0
