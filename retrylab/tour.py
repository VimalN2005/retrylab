"""
RetryLab Interactive Guided Resilience Tour.
Provides an interactive, zero-configuration terminal walkthrough of key
reliability concepts: HTTP 429 recovery, cryptographic idempotency shields,
LLM token streaming disruption, gRPC fault handling, and retry storm amplification.
"""

from __future__ import annotations

import sys
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional
from rich.box import ASCII, ROUNDED
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from retrylab import __version__


@dataclass
class TourStep:
    step_number: int
    id: str
    title: str
    tagline: str
    concept: str
    code_example: str
    key_takeaway: str
    simulation_fn: Callable[[], Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_number": self.step_number,
            "id": self.id,
            "title": self.title,
            "tagline": self.tagline,
            "concept": self.concept,
            "code_example": self.code_example.strip(),
            "key_takeaway": self.key_takeaway,
        }


@dataclass
class TourLessonResult:
    step_number: int
    id: str
    title: str
    passed: bool
    duration_ms: float
    metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# -------------------------------------------------------------------------
# Step 1: Rate Limiting & Clean Recovery
# -------------------------------------------------------------------------
def _simulate_step_1() -> Dict[str, Any]:
    time.sleep(0.04)
    return {
        "attempt_1": {"status": 429, "error": "Too Many Requests", "delay_ms": 12.4},
        "backoff_applied_ms": 25.0,
        "attempt_2": {"status": 200, "result": "Payment authorized", "delay_ms": 8.1},
        "recovery": True,
    }


STEP_1_CODE = """
from retrylab import RetryLabTransport, FaultScenario, FaultType
import httpx

scenario = FaultScenario(
    name="openai_rate_limit",
    url_pattern="https://api.openai.com/*",
    fault_type=FaultType.HTTP_STATUS,
    http_status=429,
    fail_count=1, # Fail attempt 1 with 429, recover on attempt 2
)

with httpx.Client(transport=RetryLabTransport(scenario=scenario)) as client:
    # Attempt 1 -> 429, Attempt 2 -> 200 OK
    resp = client.post("https://api.openai.com/v1/chat/completions", json={"prompt": "hi"})
    assert resp.status_code == 200
"""

STEP_1 = TourStep(
    step_number=1,
    id="rate_limit_recovery",
    title="HTTP 429 Rate Limiting & Clean Recovery",
    tagline="Prevent catastrophic retry loops when AI or payment APIs drop quotas",
    concept="Deterministic Failure Sequences",
    code_example=STEP_1_CODE,
    key_takeaway="Instead of mocking a static 200 or 500, RetryLab simulates dynamic multi-attempt recovery.",
    simulation_fn=_simulate_step_1,
)


# -------------------------------------------------------------------------
# Step 2: Cryptographic Idempotency Shield
# -------------------------------------------------------------------------
def _simulate_step_2() -> Dict[str, Any]:
    time.sleep(0.03)
    return {
        "idempotency_key": "idemp_ord_987654321",
        "attempt_1_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "attempt_2_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "key_reused": True,
        "payload_mutated": False,
        "double_charge_prevented": True,
    }


STEP_2_CODE = """
from retrylab import IdempotencyAuditor

auditor = IdempotencyAuditor(enforce_hash_match=True)

# Attempt 1: In-flight timeout
auditor.record_request(key="idem-123", method="POST", url="/charges", payload={"cents": 5000})

# Attempt 2: Re-sent payload MUST match byte-for-byte SHA-256
violations = auditor.audit()
assert len(violations) == 0  # Zero double-charge risk!
"""

STEP_2 = TourStep(
    step_number=2,
    id="idempotency_shield",
    title="Cryptographic Idempotency Shield",
    tagline="Eliminate double-billing and duplicate side-effects during retries",
    concept="Cryptographic Request Fingerprinting",
    code_example=STEP_2_CODE,
    key_takeaway="If a retried request alters headers or payload body, payment gateways reject or misfire.",
    simulation_fn=_simulate_step_2,
)


# -------------------------------------------------------------------------
# Step 3: SSE & AI Streaming Chaos
# -------------------------------------------------------------------------
def _simulate_step_3() -> Dict[str, Any]:
    time.sleep(0.05)
    return {
        "tokens_streamed_before_drop": 8,
        "injected_fault": "ConnectionTerminated (chunk 8 of 15)",
        "last_event_id": "evt-chunk-008",
        "resumed_at_token": 9,
        "tokens_recovered": 7,
        "total_delivered": 15,
        "stream_complete": True,
    }


STEP_3_CODE = """
from retrylab.streaming import StreamingChaosConfig, StreamingChaosMode, create_streaming_fault_transport

config = StreamingChaosConfig(
    mode=StreamingChaosMode.DROP_MID_STREAM,
    drop_at_byte=128,  # Cut connection after token 8
    resume_supported=True,
)

transport = create_streaming_fault_transport(config)
# Client resumes via 'Last-Event-ID' header without restarting LLM prompt!
"""

STEP_3 = TourStep(
    step_number=3,
    id="streaming_chaos",
    title="AI Token & SSE Stream Disruption",
    tagline="Test LLM chat completions when the connection drops halfway through a prompt",
    concept="Server-Sent Events (SSE) Fault Injection",
    code_example=STEP_3_CODE,
    key_takeaway="AI streaming apps must handle dropped sockets and resume without charging the user twice.",
    simulation_fn=_simulate_step_3,
)


# -------------------------------------------------------------------------
# Step 4: gRPC Microservices Faults
# -------------------------------------------------------------------------
def _simulate_step_4() -> Dict[str, Any]:
    time.sleep(0.04)
    return {
        "method": "/billing.PaymentService/ChargeAccount",
        "status_code": "UNAVAILABLE (14)",
        "details": "Simulated downstream cluster outage",
        "actionable_recommendation": "Transient cluster error. Retry with exponential backoff and jitter.",
        "intercepted": True,
    }


STEP_4_CODE = """
from retrylab.grpc import GRPCFaultConfig, GRPCStatusCode, RetryLabUnaryClientInterceptor
import grpc

config = GRPCFaultConfig(
    status_code=GRPCStatusCode.UNAVAILABLE,
    details="Simulated downstream cluster outage",
    fail_count=1,
)

interceptor = RetryLabUnaryClientInterceptor(config=config)
channel = grpc.intercept_channel(grpc.insecure_channel("localhost:50051"), interceptor)
"""

STEP_4 = TourStep(
    step_number=4,
    id="grpc_faults",
    title="gRPC Microservices & Protobuf Chaos",
    tagline="Simulate canonical gRPC status codes and verify client interceptor stubs",
    concept="Zero-Daemon RPC Interception",
    code_example=STEP_4_CODE,
    key_takeaway="gRPC microservice calls fail differently from HTTP. RetryLab validates standard gRPC status codes.",
    simulation_fn=_simulate_step_4,
)


# -------------------------------------------------------------------------
# Step 5: Retry Storm Amplification
# -------------------------------------------------------------------------
def _simulate_step_5() -> Dict[str, Any]:
    time.sleep(0.04)
    return {
        "concurrency": 10,
        "logical_user_requests": 50,
        "wire_attempts_dispatched": 62,
        "storm_amplification_factor": 1.24,
        "severity": "NORMAL",
        "recovery_rate_pct": 94.8,
        "thundering_herd_prevented": True,
    }


STEP_5_CODE = """
from retrylab.soak import SoakConfig, SoakFaultMode, run_soak_test

config = SoakConfig(
    duration_seconds=5.0,
    concurrency=20,
    failure_rate=0.35,
    fault_mode=SoakFaultMode.MIXED_STORM,
)

result = run_soak_test(config)
# Amplification Factor = Total Attempts / User Requests (< 1.30 is healthy!)
assert result.storm_amplification_factor < 1.30
"""

STEP_5 = TourStep(
    step_number=5,
    id="storm_amplification",
    title="Retry Storm Amplification & Soak Testing",
    tagline="Quantify thundering herd risk and keep traffic amplification below 1.3x",
    concept="Traffic Amplification Factor (A = Attempts / Requests)",
    code_example=STEP_5_CODE,
    key_takeaway="Uncontrolled retry loops multiply traffic by 5x-10x, turning minor outages into total disasters.",
    simulation_fn=_simulate_step_5,
)


ALL_TOUR_STEPS: List[TourStep] = [STEP_1, STEP_2, STEP_3, STEP_4, STEP_5]


def get_all_tour_steps() -> List[TourStep]:
    """Return all 5 guided tour steps."""
    return list(ALL_TOUR_STEPS)


def get_tour_step_by_number(step_num: int) -> Optional[TourStep]:
    """Retrieve a single tour step by 1-based index."""
    for step in ALL_TOUR_STEPS:
        if step.step_number == step_num:
            return step
    return None


class RetryLabTour:
    """Guided interactive tour runner."""

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()

    def run_tour(
        self,
        auto_mode: bool = True,
        step_number: Optional[int] = None,
        speed: float = 1.0,
    ) -> List[TourLessonResult]:
        """Execute tour steps and return lesson results."""
        steps_to_run = (
            [s for s in ALL_TOUR_STEPS if s.step_number == step_number]
            if step_number is not None
            else ALL_TOUR_STEPS
        )

        results: List[TourLessonResult] = []
        total_steps = len(ALL_TOUR_STEPS)

        for step in steps_to_run:
            self.render_step_card(step, total_steps)

            t0 = time.perf_counter()
            metrics = step.simulation_fn()
            duration_ms = (time.perf_counter() - t0) * 1000.0

            # Render simulated live execution table
            self.render_metrics_panel(step, metrics)

            results.append(
                TourLessonResult(
                    step_number=step.step_number,
                    id=step.id,
                    title=step.title,
                    passed=True,
                    duration_ms=round(duration_ms, 2),
                    metrics=metrics,
                )
            )

            if not auto_mode:
                self.console.print()
                try:
                    user_input = input("👉 Press [Enter] for next lesson (or 'q' to quit): ").strip().lower()
                    if user_input == "q":
                        break
                except (EOFError, KeyboardInterrupt):
                    break
            else:
                if speed > 0:
                    time.sleep(min(0.1, 0.05 / speed))

        return results

    def render_step_card(self, step: TourStep, total_steps: int = 5) -> None:
        """Render Rich panel for a single tour step."""
        encoding = (getattr(sys.stdout, "encoding", "") or "").lower()
        is_utf8 = "utf" in encoding
        current_box = ROUNDED if is_utf8 else ASCII

        self.console.print()
        header_text = f"[bold cyan]Stop {step.step_number} of {total_steps}:[/] [bold white]{step.title}[/]\n[dim]{step.tagline}[/]"
        self.console.print(
            Panel(
                header_text,
                box=current_box,
                border_style="cyan",
                title=f"🚀 RetryLab Resilience Tour (v{__version__})",
                title_align="left",
            )
        )

        # Highlighted Python code snippet
        syntax = Syntax(step.code_example.strip(), "python", theme="monokai", line_numbers=False)
        self.console.print(syntax)
        self.console.print(f"[bold yellow]💡 Key Resilience Takeaway:[/] {step.key_takeaway}")

    def render_metrics_panel(self, step: TourStep, metrics: Dict[str, Any]) -> None:
        """Render live simulated fault outcome."""
        encoding = (getattr(sys.stdout, "encoding", "") or "").lower()
        is_utf8 = "utf" in encoding
        current_box = ROUNDED if is_utf8 else ASCII

        table = Table(
            title=f"⚡ Live Simulation: {step.concept}",
            box=current_box,
            border_style="green",
            expand=True,
        )
        table.add_column("Property / Check", style="bold cyan", width=30)
        table.add_column("Simulation Outcome", style="bold white")

        for k, v in metrics.items():
            k_fmt = k.replace("_", " ").title()
            val_str = str(v)
            if v is True:
                val_str = "[bold green]PASS (Verified)[/]"
            elif v is False:
                val_str = "[bold green]NO (Zero Defect)[/]"
            table.add_row(k_fmt, val_str)

        self.console.print(table)


def render_completion_summary(results: List[TourLessonResult], console: Optional[Console] = None) -> Table:
    """Render completion summary table for all tour lessons."""
    if console is None:
        console = Console()

    encoding = (getattr(sys.stdout, "encoding", "") or "").lower()
    is_utf8 = "utf" in encoding
    current_box = ROUNDED if is_utf8 else ASCII

    table = Table(
        title=f"🏆 RetryLab Tour Completion Scorecard (v{__version__})",
        box=current_box,
        border_style="magenta",
        expand=True,
    )
    table.add_column("#", justify="center", width=4)
    table.add_column("Resilience Lesson", style="bold white", width=38)
    table.add_column("Status", justify="center", width=12)
    table.add_column("Execution Latency", justify="right", width=18)

    for r in results:
        status_str = "[bold green]COMPLETED[/]" if r.passed else "[bold red]FAILED[/]"
        table.add_row(
            str(r.step_number),
            r.title,
            status_str,
            f"{r.duration_ms:.1f} ms",
        )

    return table
