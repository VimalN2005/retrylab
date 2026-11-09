"""
RetryLab Polyglot Latency & Throughput Benchmark Engine.
Measures nanosecond/microsecond interception overhead, percentiles (P50, P90, P95, P99),
and throughput across Python, Go, and TypeScript SDKs.
"""

from __future__ import annotations

import json
import math
import shutil
import statistics
import subprocess
import sys
import time
import tracemalloc
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
import httpx
from rich.box import ROUNDED, ASCII
from rich.console import Console
from rich.table import Table

from retrylab.drift import SchemaDriftDetector
from retrylab.idempotency import IdempotencyAuditor
from retrylab.models import FaultScenario, FaultType, RecordedRequest
from retrylab.transport import RetryLabTransport


def _is_utf8_console() -> bool:
    encoding = (getattr(sys.stdout, "encoding", "") or "").lower()
    return "utf" in encoding


def _glyph(utf8_symbol: str, ascii_fallback: str) -> str:
    return utf8_symbol if _is_utf8_console() else ascii_fallback


def _safe_box():
    return ROUNDED if _is_utf8_console() else ASCII


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
    """Calculate percentiles and throughput from raw microsecond measurements."""
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

        baseline_metrics = self.benchmark_baseline()
        report.benchmarks["baseline_transport"] = baseline_metrics
        report.benchmarks["retrylab_passthrough"] = self.benchmark_passthrough(baseline_mean=baseline_metrics.mean_us)
        report.benchmarks["retrylab_fault_injection"] = self.benchmark_fault_injection(baseline_mean=baseline_metrics.mean_us)
        report.benchmarks["idempotency_auditor"] = self.benchmark_idempotency_auditor()
        report.benchmarks["schema_drift_detector"] = self.benchmark_schema_drift()

        return report

    def benchmark_baseline(self) -> LatencyMetrics:
        transport = DummyBaselineTransport()
        req = httpx.Request("GET", "https://api.stripe.com/v1/charges")

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
            fail_count=999999,
        )
        transport = RetryLabTransport(scenario=scenario)
        req = httpx.Request("POST", "https://api.stripe.com/v1/charges")

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
        payload = b'{"customer": "cus_999", "amount": 2000, "currency": "usd"}'

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
        baseline_resp = {"id": "ch_12345", "amount": 2000, "status": "succeeded"}
        drifted_resp = {"id": "ch_12345", "amount": "2000", "status": "succeeded"}

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


def run_go_benchmark(sdk_dir: Path, iterations: int = 1000) -> Optional[Dict[str, Any]]:
    """Execute native Go SDK benchmark runner binary and return JSON metrics."""
    if not shutil.which("go"):
        return None

    cmd = ["go", "run", "cmd/benchmark/main.go", f"--iterations={iterations}", "--json"]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(sdk_dir),
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        return json.loads(proc.stdout)
    except Exception:
        return None


def run_ts_benchmark(sdk_dir: Path, iterations: int = 1000) -> Optional[Dict[str, Any]]:
    """Execute native TypeScript/Node.js SDK benchmark script and return JSON metrics."""
    if not shutil.which("node"):
        return None

    cmd = ["node", "benchmark/benchmark.ts", "--iterations", str(iterations), "--json"]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(sdk_dir),
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        return json.loads(proc.stdout)
    except Exception:
        return None


def run_polyglot_benchmark(
    languages: Optional[List[str]] = None,
    iterations: int = 1000,
    repo_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Execute unified multi-language benchmark suite."""
    if repo_root is None:
        repo_root = Path(__file__).resolve().parent.parent

    target_langs = [l.lower() for l in (languages or ["all"])]
    run_all = "all" in target_langs

    report: Dict[str, Any] = {
        "title": "RetryLab Polyglot SDK Latency & Overhead Benchmark",
        "timestamp": time.time(),
        "iterations": iterations,
        "results": {},
    }

    # Python
    if run_all or "python" in target_langs:
        py_runner = PythonBenchmarkRunner(iterations=iterations)
        report["results"]["python"] = py_runner.run_all().to_dict()

    # Go
    if run_all or "go" in target_langs:
        go_sdk_dir = repo_root / "sdk" / "go"
        if go_sdk_dir.exists():
            go_data = run_go_benchmark(go_sdk_dir, iterations=iterations)
            if go_data:
                report["results"]["go"] = go_data

    # TypeScript
    if run_all or "ts" in target_langs or "typescript" in target_langs:
        ts_sdk_dir = repo_root / "sdk" / "ts"
        if ts_sdk_dir.exists():
            ts_data = run_ts_benchmark(ts_sdk_dir, iterations=iterations)
            if ts_data:
                report["results"]["typescript"] = ts_data

    return report


def render_benchmark_table(polyglot_data: Dict[str, Any], console: Optional[Console] = None) -> Table:
    """Render a clean Rich table summarizing latency percentiles and throughput."""
    if console is None:
        console = Console()

    unit = _glyph("µs", "us")
    title_prefix = _glyph("🏎️ ", "")

    table = Table(
        title=f"{title_prefix}RetryLab Polyglot SDK Performance & Latency Benchmark",
        box=_safe_box(),
        expand=True,
        border_style="cyan",
    )

    table.add_column("Language", style="bold cyan", width=12)
    table.add_column("Component / Scenario", style="bold white", width=26)
    table.add_column(f"Mean ({unit})", justify="right", width=11)
    table.add_column(f"P50 ({unit})", justify="right", width=10)
    table.add_column(f"P99 ({unit})", justify="right", width=10)
    table.add_column("Throughput (req/s)", justify="right", width=18)
    table.add_column("Overhead", justify="right", width=12)
    table.add_column("Verdict", justify="center", width=10)

    for lang_name, lang_report in polyglot_data.get("results", {}).items():
        benchmarks = lang_report.get("benchmarks", {})
        display_lang = lang_name.upper()

        for b_name, metrics in benchmarks.items():
            mean_us = metrics.get("mean_us", 0.0)
            p50_us = metrics.get("p50_us", 0.0)
            p99_us = metrics.get("p99_us", 0.0)
            rps = metrics.get("throughput_rps", 0.0)
            overhead_us = metrics.get("overhead_us", 0.0)

            clean_name = b_name.replace("_", " ").title()
            verdict = "[bold green]PASS[/]" if mean_us < 1000.0 else "[bold red]SLOW[/]"
            overhead_str = f"+{overhead_us:.2f} {unit}" if overhead_us > 0 else f"0.0 {unit} (Base)"

            table.add_row(
                display_lang,
                clean_name,
                f"{mean_us:.2f}",
                f"{p50_us:.2f}",
                f"{p99_us:.2f}",
                f"{rps:,.1f}",
                overhead_str,
                verdict,
            )

    return table
