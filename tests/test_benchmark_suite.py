"""
Unit tests for RetryLab Polyglot Benchmark Suite.
"""

from benchmarks.benchmark_suite import (
    BenchmarkReport,
    LatencyMetrics,
    PythonBenchmarkRunner,
    compute_percentiles,
)


def test_compute_percentiles_calculation():
    """Verify statistical accuracy of percentile and throughput math."""
    durations = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]
    metrics = compute_percentiles(durations, baseline_mean_us=20.0, peak_kb=128.5)

    assert metrics.iterations == 10
    assert metrics.min_us == 10.0
    assert metrics.max_us == 100.0
    assert metrics.mean_us == 55.0
    assert metrics.p50_us == 55.0
    assert metrics.p90_us == 91.0
    assert metrics.overhead_us == 35.0
    assert metrics.memory_peak_kb == 128.5
    assert metrics.throughput_rps > 0


def test_compute_percentiles_empty():
    """Verify empty durations gracefully return zero metrics."""
    metrics = compute_percentiles([])
    assert metrics.iterations == 0
    assert metrics.mean_us == 0
    assert metrics.p50_us == 0
    assert metrics.throughput_rps == 0


def test_python_benchmark_runner():
    """Verify PythonBenchmarkRunner completes all benchmark phases."""
    runner = PythonBenchmarkRunner(iterations=10, warmup=2)
    report = runner.run_all()

    assert report.language == "python"
    assert report.iterations == 10
    assert "baseline_transport" in report.benchmarks
    assert "retrylab_passthrough" in report.benchmarks
    assert "retrylab_fault_injection" in report.benchmarks
    assert "idempotency_auditor" in report.benchmarks
    assert "schema_drift_detector" in report.benchmarks

    base = report.benchmarks["baseline_transport"]
    assert base.iterations == 10
    assert base.mean_us > 0
    assert base.p50_us > 0

    d = report.to_dict()
    assert d["language"] == "python"
    assert len(d["benchmarks"]) == 5
