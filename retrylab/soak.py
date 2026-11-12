"""
RetryLab Soak & Stress Testing Engine.
Simulates high-concurrency sustained traffic, prolonged rate-limiting (429),
service unavailability (503), cascading failures, and measures "Retry Storm"
amplification factor under load.
"""

from __future__ import annotations

import enum
import math
import random
import statistics
import sys
import time
import tracemalloc
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple
from rich.box import ASCII, ROUNDED
from rich.console import Console
from rich.table import Table

from retrylab import __version__


class SoakFaultMode(str, enum.Enum):
    RATE_LIMIT_429 = "429_RATE_LIMIT"
    SERVICE_UNAVAILABLE_503 = "503_UNAVAILABLE"
    TIMEOUT = "TIMEOUT"
    CONNECTION_RESET = "CONNECTION_RESET"
    MIXED_STORM = "MIXED_STORM"


@dataclass
class SoakConfig:
    duration_seconds: float = 3.0
    concurrency: int = 10
    total_requests: Optional[int] = None
    request_interval_ms: float = 10.0
    failure_rate: float = 0.35  # 35% injected faults
    max_retries: int = 3
    backoff_base_ms: float = 15.0
    fault_mode: SoakFaultMode = SoakFaultMode.MIXED_STORM
    burst_enabled: bool = True
    burst_interval_seconds: float = 1.0
    burst_multiplier: float = 1.8
    seed: Optional[int] = 42

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["fault_mode"] = self.fault_mode.value
        return d


@dataclass
class RequestSample:
    request_id: str
    worker_id: int
    attempt: int
    status_code: int
    latency_ms: float
    is_retry: bool
    is_recovered: bool
    error_kind: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SoakResult:
    duration_seconds: float
    concurrency: int
    total_user_requests: int
    total_network_attempts: int
    successful_requests: int  # Clean 200 on attempt 1
    recovered_requests: int   # Succeeded on attempt 2+
    failed_requests: int      # Exhausted retries or permanently failed
    storm_amplification_factor: float  # total_network_attempts / total_user_requests
    storm_severity: str       # NORMAL, ELEVATED, DANGEROUS, CRITICAL
    recovery_rate: float      # % of failed initial requests that recovered
    throughput_rps: float
    p50_latency_ms: float
    p90_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    max_latency_ms: float
    status_distribution: Dict[int, int] = field(default_factory=dict)
    memory_baseline_mb: float = 0.0
    memory_final_mb: float = 0.0
    memory_growth_mb: float = 0.0
    samples: List[RequestSample] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": __version__,
            "duration_seconds": round(self.duration_seconds, 3),
            "concurrency": self.concurrency,
            "total_user_requests": self.total_user_requests,
            "total_network_attempts": self.total_network_attempts,
            "successful_requests": self.successful_requests,
            "recovered_requests": self.recovered_requests,
            "failed_requests": self.failed_requests,
            "storm_amplification_factor": round(self.storm_amplification_factor, 3),
            "storm_severity": self.storm_severity,
            "recovery_rate_pct": round(self.recovery_rate, 2),
            "throughput_rps": round(self.throughput_rps, 1),
            "latency": {
                "p50_ms": round(self.p50_latency_ms, 2),
                "p90_ms": round(self.p90_latency_ms, 2),
                "p95_ms": round(self.p95_latency_ms, 2),
                "p99_ms": round(self.p99_latency_ms, 2),
                "max_ms": round(self.max_latency_ms, 2),
            },
            "status_distribution": self.status_distribution,
            "memory": {
                "baseline_mb": round(self.memory_baseline_mb, 3),
                "final_mb": round(self.memory_final_mb, 3),
                "growth_mb": round(self.memory_growth_mb, 3),
            },
            "sample_count": len(self.samples),
        }


def calculate_storm_severity(factor: float) -> str:
    """Categorize retry storm traffic amplification factor."""
    if factor < 1.30:
        return "NORMAL"
    elif factor < 2.00:
        return "ELEVATED"
    elif factor < 3.50:
        return "DANGEROUS"
    return "CRITICAL"


def _simulate_backend_response(
    fault_mode: SoakFaultMode,
    is_burst: bool,
    base_failure_rate: float,
    burst_multiplier: float,
    rng: random.Random,
    attempt: int,
) -> Tuple[int, Optional[str], float]:
    """
    Simulate upstream response status, error, and latency.
    With exponential backoff on retries, probability of eventual recovery increases.
    """
    effective_rate = base_failure_rate * (burst_multiplier if is_burst else 1.0)
    effective_rate = min(0.95, effective_rate)

    # Recovery decay on successive retries: retry 2 has lower fail prob, retry 3 lower still
    decay = 0.65 ** (attempt - 1)
    fail_prob = effective_rate * decay

    if rng.random() > fail_prob:
        # Success 200 OK
        lat = rng.uniform(2.0, 15.0)
        return 200, None, lat

    # Injected fault selection
    lat = rng.uniform(5.0, 35.0)
    if fault_mode == SoakFaultMode.RATE_LIMIT_429:
        return 429, "Rate limit exceeded (HTTP 429)", lat
    elif fault_mode == SoakFaultMode.SERVICE_UNAVAILABLE_503:
        return 503, "Service temporarily unavailable (HTTP 503)", lat
    elif fault_mode == SoakFaultMode.TIMEOUT:
        return 504, "Gateway timeout (HTTP 504)", lat + 25.0
    elif fault_mode == SoakFaultMode.CONNECTION_RESET:
        return 0, "Connection reset by peer", lat

    # MIXED_STORM: realistic blend of 429 (50%), 503 (30%), 504 (15%), reset (5%)
    r = rng.random()
    if r < 0.50:
        return 429, "Rate limit exceeded (HTTP 429)", lat
    elif r < 0.80:
        return 503, "Service overloaded (HTTP 503)", lat
    elif r < 0.95:
        return 504, "Upstream timeout (HTTP 504)", lat + 20.0
    return 0, "Connection reset by peer", lat


def _worker_task(
    worker_id: int,
    config: SoakConfig,
    start_time: float,
    deadline: float,
    max_requests_per_worker: Optional[int],
    custom_callable: Optional[Callable[[int, int], Tuple[int, Optional[str], float]]],
) -> List[RequestSample]:
    """Single worker executing simulated client requests and retry policies."""
    rng = random.Random((config.seed or 1337) + worker_id * 31)
    samples: List[RequestSample] = []
    req_index = 0

    while True:
        now = time.perf_counter()
        if now >= deadline:
            break
        if max_requests_per_worker is not None and req_index >= max_requests_per_worker:
            break

        req_index += 1
        req_id = f"req-w{worker_id:02d}-{req_index:04d}"

        # Determine burst status based on time elapsed
        elapsed = now - start_time
        is_burst = False
        if config.burst_enabled and config.burst_interval_seconds > 0:
            cycle = elapsed % (config.burst_interval_seconds * 2.0)
            is_burst = cycle < config.burst_interval_seconds

        # Client attempt loop (1 initial + up to max_retries)
        recovered = False
        for attempt in range(1, config.max_retries + 2):
            t0 = time.perf_counter()
            if custom_callable is not None:
                status, err, lat = custom_callable(worker_id, attempt)
            else:
                status, err, lat = _simulate_backend_response(
                    fault_mode=config.fault_mode,
                    is_burst=is_burst,
                    base_failure_rate=config.failure_rate,
                    burst_multiplier=config.burst_multiplier,
                    rng=rng,
                    attempt=attempt,
                )

            is_retry = attempt > 1
            if status == 200 and is_retry:
                recovered = True

            samples.append(
                RequestSample(
                    request_id=req_id,
                    worker_id=worker_id,
                    attempt=attempt,
                    status_code=status,
                    latency_ms=lat,
                    is_retry=is_retry,
                    is_recovered=recovered,
                    error_kind=err,
                )
            )

            if status == 200:
                break  # Succeeded, stop retrying

            # Client exponential backoff with jitter before next retry
            if attempt <= config.max_retries:
                backoff_ms = config.backoff_base_ms * (2.0 ** (attempt - 1))
                jitter = rng.uniform(0.7, 1.3)
                sleep_sec = (backoff_ms * jitter) / 1000.0
                time.sleep(min(0.05, sleep_sec))

        # Pace requests between logical calls
        if config.request_interval_ms > 0:
            time.sleep(config.request_interval_ms / 1000.0)

    return samples


def run_soak_test(
    config: Optional[SoakConfig] = None,
    client_callable: Optional[Callable[[int, int], Tuple[int, Optional[str], float]]] = None,
) -> SoakResult:
    """
    Execute high-concurrency soak & stress test.
    Tracks requests, retry amplification, latencies, and memory stability.
    """
    if config is None:
        config = SoakConfig()

    tracemalloc.start()
    mem_start_bytes, _ = tracemalloc.get_traced_memory()

    start_time = time.perf_counter()
    deadline = start_time + max(0.5, config.duration_seconds)

    max_reqs_per_worker = None
    if config.total_requests is not None and config.total_requests > 0:
        max_reqs_per_worker = math.ceil(config.total_requests / max(1, config.concurrency))

    all_samples: List[RequestSample] = []
    with ThreadPoolExecutor(max_workers=config.concurrency) as pool:
        futures = [
            pool.submit(
                _worker_task,
                worker_id=w,
                config=config,
                start_time=start_time,
                deadline=deadline,
                max_requests_per_worker=max_reqs_per_worker,
                custom_callable=client_callable,
            )
            for w in range(config.concurrency)
        ]
        for f in as_completed(futures):
            all_samples.extend(f.result())

    end_time = time.perf_counter()
    duration = end_time - start_time

    mem_end_bytes, _ = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    baseline_mb = mem_start_bytes / (1024 * 1024)
    final_mb = mem_end_bytes / (1024 * 1024)
    growth_mb = max(0.0, final_mb - baseline_mb)

    # Group samples by request_id to calculate logical vs network metrics
    req_attempts: Dict[str, List[RequestSample]] = {}
    for s in all_samples:
        req_attempts.setdefault(s.request_id, []).append(s)

    total_user_requests = len(req_attempts)
    total_network_attempts = len(all_samples)

    successful_requests = 0
    recovered_requests = 0
    failed_requests = 0
    status_distribution: Dict[int, int] = {}
    latencies: List[float] = []

    for req_id, attempts in req_attempts.items():
        first_attempt = attempts[0]
        final_attempt = attempts[-1]

        if first_attempt.status_code == 200:
            successful_requests += 1
        elif final_attempt.status_code == 200:
            recovered_requests += 1
        else:
            failed_requests += 1

    for s in all_samples:
        status_distribution[s.status_code] = status_distribution.get(s.status_code, 0) + 1
        latencies.append(s.latency_ms)

    # Amplification Factor: network attempts / logical requests
    if total_user_requests > 0:
        storm_factor = total_network_attempts / total_user_requests
    else:
        storm_factor = 1.0

    severity = calculate_storm_severity(storm_factor)

    # Recovery Rate %
    initial_failures = total_user_requests - successful_requests
    if initial_failures > 0:
        recovery_rate = (recovered_requests / initial_failures) * 100.0
    else:
        recovery_rate = 100.0

    throughput = total_network_attempts / max(0.001, duration)

    # Percentiles
    if latencies:
        latencies.sort()
        p50 = statistics.median(latencies)
        p90 = latencies[int(len(latencies) * 0.90)]
        p95 = latencies[int(len(latencies) * 0.95)]
        p99 = latencies[min(len(latencies) - 1, int(len(latencies) * 0.99))]
        max_lat = max(latencies)
    else:
        p50 = p90 = p95 = p99 = max_lat = 0.0

    return SoakResult(
        duration_seconds=duration,
        concurrency=config.concurrency,
        total_user_requests=total_user_requests,
        total_network_attempts=total_network_attempts,
        successful_requests=successful_requests,
        recovered_requests=recovered_requests,
        failed_requests=failed_requests,
        storm_amplification_factor=storm_factor,
        storm_severity=severity,
        recovery_rate=recovery_rate,
        throughput_rps=throughput,
        p50_latency_ms=p50,
        p90_latency_ms=p90,
        p95_latency_ms=p95,
        p99_latency_ms=p99,
        max_latency_ms=max_lat,
        status_distribution=status_distribution,
        memory_baseline_mb=baseline_mb,
        memory_final_mb=final_mb,
        memory_growth_mb=growth_mb,
        samples=all_samples,
    )


def render_soak_table(result: SoakResult, console: Optional[Console] = None) -> Table:
    """Render Rich table visualizing soak test results & storm amplification."""
    if console is None:
        console = Console()

    encoding = (getattr(sys.stdout, "encoding", "") or "").lower()
    is_utf8 = "utf" in encoding
    current_box = ROUNDED if is_utf8 else ASCII

    table = Table(
        title=f"⚡ RetryLab Soak & Stress Test Report (v{__version__})",
        box=current_box,
        expand=True,
        border_style="magenta",
    )
    table.add_column("Metric", style="bold cyan", width=28)
    table.add_column("Value", style="bold white", width=22)
    table.add_column("Assessment / Resilience Diagnosis", style="white")

    # Duration & Concurrency
    table.add_row(
        "Duration & Workers",
        f"{result.duration_seconds:.2f}s | {result.concurrency} workers",
        f"Completed sustained soak loop with {result.concurrency} concurrent threads",
    )

    # Dispatched Requests
    table.add_row(
        "User Requests / Attempts",
        f"{result.total_user_requests:,} reqs / {result.total_network_attempts:,} att",
        f"{result.throughput_rps:,.1f} requests/sec throughput",
    )

    # Storm Amplification Factor
    severity_styles = {
        "NORMAL": "[bold green]NORMAL[/] (healthy backoff & jitter)",
        "ELEVATED": "[bold yellow]ELEVATED[/] (mild retry pressure)",
        "DANGEROUS": "[bold red]DANGEROUS[/] (retry storm detected)",
        "CRITICAL": "[bold red on white]CRITICAL[/] (catastrophic thundering herd)",
    }
    styled_sev = severity_styles.get(result.storm_severity, result.storm_severity)
    table.add_row(
        "Storm Amplification Factor",
        f"{result.storm_amplification_factor:.2f}x multiplier",
        f"Traffic amplification: {styled_sev}",
    )

    # Recovery Rate
    rec_style = "bold green" if result.recovery_rate >= 80.0 else "bold yellow" if result.recovery_rate >= 50.0 else "bold red"
    table.add_row(
        "Failure Recovery Rate",
        f"[{rec_style}]{result.recovery_rate:.1f}%[/{rec_style}]",
        f"{result.recovered_requests:,} retries recovered, {result.failed_requests:,} permanently exhausted",
    )

    # Success breakdown
    table.add_row(
        "Request Breakdown",
        f"200 OK: {result.successful_requests + result.recovered_requests:,}",
        f"Clean first-try: {result.successful_requests:,} | Recovered: {result.recovered_requests:,}",
    )

    # Status Distribution
    status_parts = []
    for code, count in sorted(result.status_distribution.items()):
        name = "Err/Reset" if code == 0 else f"HTTP {code}"
        status_parts.append(f"{name}: {count:,}")
    status_str = " | ".join(status_parts) if status_parts else "None"
    table.add_row("Status Code Distribution", f"{len(result.status_distribution)} codes", status_str)

    # Latencies
    table.add_row(
        "Latency Distribution",
        f"P50: {result.p50_latency_ms:.1f}ms | P99: {result.p99_latency_ms:.1f}ms",
        f"P90: {result.p90_latency_ms:.1f}ms | P95: {result.p95_latency_ms:.1f}ms | Max: {result.max_latency_ms:.1f}ms",
    )

    # Memory Stability
    mem_diag = "[green]STABLE[/] (zero detectable leak)" if result.memory_growth_mb < 5.0 else "[yellow]ELEVATED[/]"
    table.add_row(
        "Memory Stability",
        f"Growth: +{result.memory_growth_mb:.2f} MB",
        f"Baseline: {result.memory_baseline_mb:.2f} MB → Final: {result.memory_final_mb:.2f} MB ({mem_diag})",
    )

    return table
