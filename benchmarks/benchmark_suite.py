"""
Comprehensive Polyglot Benchmark Suite for RetryLab.
Measures latency percentiles (P50, P90, P95, P99), throughput (RPS), and memory footprint.
"""

from __future__ import annotations

import math
import statistics
import sys
import time
import tracemalloc
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

# Ensure repository root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

from retrylab.idempotency import IdempotencyAuditor
from retrylab.drift import SchemaDriftDetector
from retrylab.models import FaultScenario, FaultType, RecordedRequest
from retrylab.transport import RetryLabTransport


@dataclass
class LatencyMetrics:
    iterations: int
    mean_us: float
    p50_us: float
    p90_us: float
    p95_us: float
    p99_us: float
    min_us: float
    max_us: float
    throughput_rps: float
    overhead_us: float = 0.0
    memory_peak_kb: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BenchmarkReport:
    language: str
    timestamp: float
    iterations: int
    benchmarks: Dict[str, LatencyMetrics] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "language": self.language,
            "timestamp": self.timestamp,
            "iterations": self.iterations,
            "benchmarks": {k: v.to_dict() for k, v in self.benchmarks.items()},
        }


class DummyBaselineTransport(httpx.BaseTransport):
    """Zero-overhead baseline transport for measuring interception differential."""

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=200, content=b'{"status": "ok"}', request=request)


def compute_percentiles(durations_us: List[float], baseline_mean_us: float = 0.0, peak_kb: float = 0.0) -> LatencyMetrics:
    """Calculate rigorous percentiles and throughput from raw microsecond measurements."""
    if not durations_us:
        return LatencyMetrics(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)

    sorted_d = sorted(durations_us)
    n = len(sorted_d)

    def percentile(p: float) -> float:
        if n == 1:
            return sorted_d[0]
        k = (n - 1) * (p / 100.0)
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return sorted_d[int(k)]
        d0 = sorted_d[int(f)] * (c - k)
        d1 = sorted_d[int(c)] * (k - f)
        return d0 + d1

    mean_val = statistics.mean(sorted_d)
    total_sec = sum(sorted_d) / 1_000_000.0
    throughput = (n / total_sec) if total_sec > 0 else 0.0
    overhead = max(0.0, mean_val - baseline_mean_us) if baseline_mean_us > 0 else 0.0

    return LatencyMetrics(
        iterations=n,
        mean_us=round(mean_val, 2),
        p50_us=round(percentile(50.0), 2),
        p90_us=round(percentile(90.0), 2),
        p95_us=round(percentile(95.0), 2),
        p99_us=round(percentile(99.0), 2),
        min_us=round(sorted_d[0], 2),
        max_us=round(sorted_d[-1], 2),
        throughput_rps=round(throughput, 1),
        overhead_us=round(overhead, 2),
        memory_peak_kb=round(peak_kb, 2),
    )


class PythonBenchmarkRunner:
    """Executes high-resolution latency and memory benchmarks for Python core engine."""

    def __init__(self, iterations: int = 1000, warmup: int = 50):
        self.iterations = iterations
        self.warmup = warmup

    def run_all(self) -> BenchmarkReport:
        report = BenchmarkReport(
            language="python",
            timestamp=time.time(),
            iterations=self.iterations,
        )

        # 1. Baseline Transport
        baseline_metrics = self.benchmark_baseline()
        report.benchmarks["baseline_transport"] = baseline_metrics

        # 2. RetryLab Transport Passthrough
        report.benchmarks["retrylab_passthrough"] = self.benchmark_passthrough(
            baseline_mean=baseline_metrics.mean_us
        )

        # 3. RetryLab Transport Fault Injection
        report.benchmarks["retrylab_fault_injection"] = self.benchmark_fault_injection(
            baseline_mean=baseline_metrics.mean_us
        )

        # 4. Cryptographic Idempotency Auditor
        report.benchmarks["idempotency_auditor"] = self.benchmark_idempotency_auditor()

        # 5. Schema Drift Detector
        report.benchmarks["schema_drift_detector"] = self.benchmark_schema_drift()

        return report

    def benchmark_baseline(self) -> LatencyMetrics:
        transport = DummyBaselineTransport()
        req = httpx.Request("GET", "https://api.stripe.com/v1/charges")

        # Warmup
        for _ in range(self.warmup):
            transport.handle_request(req)

        durations_us: List[float] = []
        tracemalloc.start()
        for _ in range(self.iterations):
            t0 = time.perf_counter_ns()
            transport.handle_request(req)
            t1 = time.perf_counter_ns()
            durations_us.append((t1 - t0) / 1000.0)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        return compute_percentiles(durations_us, baseline_mean_us=0.0, peak_kb=peak / 1024.0)

    def benchmark_passthrough(self, baseline_mean: float) -> LatencyMetrics:
        base = DummyBaselineTransport()
        scenario = FaultScenario(
            target="https://api.unmatched.internal/*",
            fault=FaultType.TIMEOUT,
        )
        transport = RetryLabTransport(scenario=scenario, passthrough_transport=base)
        req = httpx.Request("GET", "https://api.stripe.com/v1/charges")

        # Warmup
        for _ in range(self.warmup):
            transport.handle_request(req)

        durations_us: List[float] = []
        tracemalloc.start()
        for _ in range(self.iterations):
            t0 = time.perf_counter_ns()
            transport.handle_request(req)
            t1 = time.perf_counter_ns()
            durations_us.append((t1 - t0) / 1000.0)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        return compute_percentiles(durations_us, baseline_mean_us=baseline_mean, peak_kb=peak / 1024.0)

    def benchmark_fault_injection(self, baseline_mean: float) -> LatencyMetrics:
        scenario = FaultScenario(
            target="https://api.stripe.com/*",
            fault=FaultType.SERVER_ERROR_500,
            fail_count=999999,  # Always inject
        )
        transport = RetryLabTransport(scenario=scenario)
        req = httpx.Request("POST", "https://api.stripe.com/v1/charges")

        # Warmup
        for _ in range(self.warmup):
            transport.handle_request(req)

        durations_us: List[float] = []
        tracemalloc.start()
        for _ in range(self.iterations):
            t0 = time.perf_counter_ns()
            transport.handle_request(req)
            t1 = time.perf_counter_ns()
            durations_us.append((t1 - t0) / 1000.0)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        return compute_percentiles(durations_us, baseline_mean_us=baseline_mean, peak_kb=peak / 1024.0)

    def benchmark_idempotency_auditor(self) -> LatencyMetrics:
        auditor = IdempotencyAuditor(idempotency_header="Idempotency-Key")
        scenario = FaultScenario(
            target="https://api.stripe.com/v1/charges",
            fault=FaultType.TIMEOUT,
            fail_count=1,
        )
        payload = b'{"customer": "cus_999", "amount": 2000, "currency": "usd", "items": [{"id": 1}, {"id": 2}]}'

        # Warmup
        for _ in range(self.warmup):
            scenario.reset()
            scenario.record_attempt("https://api.stripe.com/v1/charges", "POST", {"Idempotency-Key": "tok_bench_123"}, payload, True)
            scenario.record_attempt("https://api.stripe.com/v1/charges", "POST", {"Idempotency-Key": "tok_bench_123"}, payload, False)
            scenario.record_attempt("https://api.stripe.com/v1/charges", "POST", {"Idempotency-Key": "tok_bench_123"}, payload, False)
            auditor.assert_idempotent(scenario)

        durations_us: List[float] = []
        tracemalloc.start()
        for _ in range(self.iterations):
            scenario.reset()
            scenario.record_attempt("https://api.stripe.com/v1/charges", "POST", {"Idempotency-Key": "tok_bench_123"}, payload, True)
            scenario.record_attempt("https://api.stripe.com/v1/charges", "POST", {"Idempotency-Key": "tok_bench_123"}, payload, False)
            scenario.record_attempt("https://api.stripe.com/v1/charges", "POST", {"Idempotency-Key": "tok_bench_123"}, payload, False)
            t0 = time.perf_counter_ns()
            auditor.assert_idempotent(scenario)
            t1 = time.perf_counter_ns()
            durations_us.append((t1 - t0) / 1000.0)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        return compute_percentiles(durations_us, baseline_mean_us=0.0, peak_kb=peak / 1024.0)

    def benchmark_schema_drift(self) -> LatencyMetrics:
        detector = SchemaDriftDetector()
        baseline_resp = {
            "id": "ch_12345",
            "amount": 2000,
            "status": "succeeded",
            "metadata": {"order_id": "ord_888"},
        }
        drifted_resp = {
            "id": "ch_12345",
            "amount": "2000",  # Drift: string instead of int
            "status": "succeeded",
            "extra_field": True,
        }

        # Warmup
        for _ in range(self.warmup):
            detector.compare(baseline_resp, drifted_resp)

        durations_us: List[float] = []
        tracemalloc.start()
        for _ in range(self.iterations):
            t0 = time.perf_counter_ns()
            detector.compare(baseline_resp, drifted_resp)
            t1 = time.perf_counter_ns()
            durations_us.append((t1 - t0) / 1000.0)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        return compute_percentiles(durations_us, baseline_mean_us=0.0, peak_kb=peak / 1024.0)


if __name__ == "__main__":
    runner = PythonBenchmarkRunner(iterations=1000)
    rep = runner.run_all()
    print(f"--- RetryLab Python Benchmark ({rep.iterations} iterations) ---")
    for name, bench in rep.benchmarks.items():
        print(f"[{name}]")
        print(f"  Mean: {bench.mean_us} µs | P50: {bench.p50_us} µs | P99: {bench.p99_us} µs")
        print(f"  Throughput: {bench.throughput_rps} req/s | Overhead: {bench.overhead_us} µs | Peak Mem: {bench.memory_peak_kb} KB")
