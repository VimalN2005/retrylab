"""
RetryLab Distributed Tracing & OpenTelemetry Chaos Modeling.
Validates W3C TraceContext (traceparent/tracestate), B3, AWS X-Ray, and Datadog
header propagation across retries, simulating trace stripping, corruption, and span drift.
"""

from __future__ import annotations

import enum
import os
import random
import re
import secrets
import sys
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from rich.box import ASCII, ROUNDED
from rich.console import Console
from rich.table import Table

from retrylab import __version__


class TraceFormat(str, enum.Enum):
    W3C_TRACECONTEXT = "w3c"
    B3_SINGLE = "b3_single"
    B3_MULTI = "b3_multi"
    AWS_XRAY = "aws_xray"
    DATADOG = "datadog"


class TraceChaosMode(str, enum.Enum):
    PRESERVE_PARENT = "preserve_parent"
    STRIP_HEADER = "strip_header"
    CORRUPT_TRACE_ID = "corrupt_trace_id"
    FORCE_UNSAMPLED = "force_unsampled"
    CHILD_SPAN_DRIFT = "child_span_drift"


@dataclass
class TraceContext:
    trace_id: str  # 32 hex chars for W3C / B3 128-bit
    span_id: str   # 16 hex chars
    parent_span_id: Optional[str] = None
    sampled: bool = True
    format: TraceFormat = TraceFormat.W3C_TRACECONTEXT
    tracestate: Optional[str] = None

    @classmethod
    def generate(
        cls,
        format: TraceFormat = TraceFormat.W3C_TRACECONTEXT,
        sampled: bool = True,
        trace_id: Optional[str] = None,
        span_id: Optional[str] = None,
    ) -> TraceContext:
        """Create a fresh cryptographically random TraceContext."""
        t_id = trace_id or secrets.token_hex(16)  # 32 hex chars
        s_id = span_id or secrets.token_hex(8)   # 16 hex chars
        return cls(
            trace_id=t_id.lower(),
            span_id=s_id.lower(),
            parent_span_id=None,
            sampled=sampled,
            format=format,
        )

    def create_child_span(self) -> TraceContext:
        """Generate a new child span preserving root trace ID and linking parent."""
        return TraceContext(
            trace_id=self.trace_id,
            span_id=secrets.token_hex(8).lower(),
            parent_span_id=self.span_id,
            sampled=self.sampled,
            format=self.format,
            tracestate=self.tracestate,
        )

    def corrupt_trace_id(self) -> TraceContext:
        """Inject chaos by mutating trace ID bytes into invalid non-hex characters."""
        corrupted = "ZZ" + self.trace_id[2:]
        return TraceContext(
            trace_id=corrupted,
            span_id=self.span_id,
            parent_span_id=self.parent_span_id,
            sampled=self.sampled,
            format=self.format,
            tracestate=self.tracestate,
        )

    def to_headers(self) -> Dict[str, str]:
        """Serialize context into standard HTTP headers for the configured format."""
        if self.format == TraceFormat.W3C_TRACECONTEXT:
            flags = "01" if self.sampled else "00"
            headers = {"traceparent": f"00-{self.trace_id}-{self.span_id}-{flags}"}
            if self.tracestate:
                headers["tracestate"] = self.tracestate
            return headers

        if self.format == TraceFormat.B3_SINGLE:
            flag = "1" if self.sampled else "0"
            val = f"{self.trace_id}-{self.span_id}-{flag}"
            if self.parent_span_id:
                val += f"-{self.parent_span_id}"
            return {"b3": val}

        if self.format == TraceFormat.B3_MULTI:
            headers = {
                "X-B3-TraceId": self.trace_id,
                "X-B3-SpanId": self.span_id,
                "X-B3-Sampled": "1" if self.sampled else "0",
            }
            if self.parent_span_id:
                headers["X-B3-ParentSpanId"] = self.parent_span_id
            return headers

        if self.format == TraceFormat.AWS_XRAY:
            sample_val = "1" if self.sampled else "0"
            val = f"Root=1-{self.trace_id[:8]}-{self.trace_id[8:]};Parent={self.span_id};Sampled={sample_val}"
            return {"X-Amzn-Trace-Id": val}

        if self.format == TraceFormat.DATADOG:
            # Datadog uses 64-bit unsigned decimal integers
            t_int = int(self.trace_id[:16], 16)
            s_int = int(self.span_id, 16)
            return {
                "x-datadog-trace-id": str(t_int),
                "x-datadog-parent-id": str(s_int),
                "x-datadog-sampling-priority": "1" if self.sampled else "0",
            }

        return {}

    @classmethod
    def from_headers(cls, headers: Dict[str, str]) -> Optional[TraceContext]:
        """Parse HTTP headers into a TraceContext instance."""
        lower_headers = {k.lower(): v for k, v in headers.items()}

        # 1. W3C TraceContext: traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
        if "traceparent" in lower_headers:
            val = lower_headers["traceparent"].strip()
            parts = val.split("-")
            if len(parts) >= 4 and parts[0] == "00":
                t_id = parts[1]
                s_id = parts[2]
                flags = parts[3]
                sampled = flags in ("01", "1")
                return cls(
                    trace_id=t_id,
                    span_id=s_id,
                    sampled=sampled,
                    format=TraceFormat.W3C_TRACECONTEXT,
                    tracestate=lower_headers.get("tracestate"),
                )

        # 2. B3 Single: b3: {trace_id}-{span_id}-{sampled}-{parent_span_id}
        if "b3" in lower_headers:
            val = lower_headers["b3"].strip()
            parts = val.split("-")
            if len(parts) >= 2:
                t_id = parts[0]
                s_id = parts[1]
                sampled = parts[2] == "1" if len(parts) >= 3 else True
                parent = parts[3] if len(parts) >= 4 else None
                return cls(
                    trace_id=t_id,
                    span_id=s_id,
                    parent_span_id=parent,
                    sampled=sampled,
                    format=TraceFormat.B3_SINGLE,
                )

        # 3. B3 Multi: X-B3-TraceId, X-B3-SpanId
        if "x-b3-traceid" in lower_headers and "x-b3-spanid" in lower_headers:
            t_id = lower_headers["x-b3-traceid"]
            s_id = lower_headers["x-b3-spanid"]
            sampled = lower_headers.get("x-b3-sampled", "1") == "1"
            parent = lower_headers.get("x-b3-parentspanid")
            return cls(
                trace_id=t_id,
                span_id=s_id,
                parent_span_id=parent,
                sampled=sampled,
                format=TraceFormat.B3_MULTI,
            )

        # 4. AWS X-Ray: X-Amzn-Trace-Id
        if "x-amzn-trace-id" in lower_headers:
            val = lower_headers["x-amzn-trace-id"]
            root_m = re.search(r"Root=1-([0-9a-fA-F]+)-([0-9a-fA-F]+)", val)
            parent_m = re.search(r"Parent=([0-9a-fA-F]+)", val)
            sampled_m = re.search(r"Sampled=([01])", val)
            if root_m:
                t_id = (root_m.group(1) + root_m.group(2)).lower()
                s_id = parent_m.group(1).lower() if parent_m else secrets.token_hex(8)
                sampled = sampled_m.group(1) == "1" if sampled_m else True
                return cls(
                    trace_id=t_id,
                    span_id=s_id,
                    sampled=sampled,
                    format=TraceFormat.AWS_XRAY,
                )

        # 5. Datadog
        if "x-datadog-trace-id" in lower_headers and "x-datadog-parent-id" in lower_headers:
            try:
                t_dec = int(lower_headers["x-datadog-trace-id"])
                s_dec = int(lower_headers["x-datadog-parent-id"])
                t_id = f"{t_dec:016x}"
                s_id = f"{s_dec:016x}"
                sampled = lower_headers.get("x-datadog-sampling-priority", "1") != "0"
                return cls(
                    trace_id=t_id,
                    span_id=s_id,
                    sampled=sampled,
                    format=TraceFormat.DATADOG,
                )
            except ValueError:
                pass

        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "sampled": self.sampled,
            "format": self.format.value,
            "tracestate": self.tracestate,
            "headers": self.to_headers(),
        }


@dataclass
class TraceViolation:
    attempt: int
    kind: str  # MISSING_HEADER, TRACE_ID_CHANGED, DUPLICATE_SPAN_ID, MALFORMED_HEADER
    message: str
    details: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TraceAuditReport:
    root_trace_id: Optional[str]
    total_attempts: int
    spans_detected: int
    passed: bool
    violations: List[TraceViolation] = field(default_factory=list)
    format_detected: Optional[str] = None
    spans: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": __version__,
            "root_trace_id": self.root_trace_id,
            "total_attempts": self.total_attempts,
            "spans_detected": self.spans_detected,
            "passed": self.passed,
            "format_detected": self.format_detected,
            "violation_count": len(self.violations),
            "violations": [v.to_dict() for v in self.violations],
            "spans": self.spans,
        }


class TraceAuditor:
    """Audits distributed tracing headers across initial calls and retry attempts."""

    def __init__(self, expected_format: Optional[TraceFormat] = None):
        self.expected_format = expected_format

    def audit_trace_sequence(self, attempts_headers: List[Dict[str, str]]) -> TraceAuditReport:
        """
        Validate distributed trace header preservation across a list of request headers.
        Verifies:
        1. Root trace_id is preserved on every attempt.
        2. Span ID is present and valid.
        3. Each retry generates a unique child span_id (or properly preserves linkage).
        """
        violations: List[TraceViolation] = []
        parsed_contexts: List[Tuple[int, Optional[TraceContext]]] = []

        for idx, hdrs in enumerate(attempts_headers, start=1):
            ctx = TraceContext.from_headers(hdrs)
            parsed_contexts.append((idx, ctx))

        # Check attempt 1
        first_attempt_num, first_ctx = parsed_contexts[0] if parsed_contexts else (1, None)
        if first_ctx is None:
            violations.append(
                TraceViolation(
                    attempt=first_attempt_num,
                    kind="MISSING_HEADER",
                    message="Initial request lacked distributed trace headers (traceparent/b3/xray)",
                )
            )
            return TraceAuditReport(
                root_trace_id=None,
                total_attempts=len(attempts_headers),
                spans_detected=0,
                passed=False,
                violations=violations,
                format_detected=None,
                spans=[],
            )

        root_trace_id = first_ctx.trace_id
        format_detected = first_ctx.format.value
        seen_span_ids: set[str] = set()
        spans_summary: List[Dict[str, Any]] = []

        for attempt_num, ctx in parsed_contexts:
            if ctx is None:
                violations.append(
                    TraceViolation(
                        attempt=attempt_num,
                        kind="MISSING_HEADER",
                        message=f"Attempt {attempt_num} dropped trace headers during retry",
                    )
                )
                continue

            spans_summary.append({
                "attempt": attempt_num,
                "trace_id": ctx.trace_id,
                "span_id": ctx.span_id,
                "parent_span_id": ctx.parent_span_id,
                "sampled": ctx.sampled,
            })

            # Verify Root Trace ID continuity
            if ctx.trace_id.lower() != root_trace_id.lower():
                violations.append(
                    TraceViolation(
                        attempt=attempt_num,
                        kind="TRACE_ID_CHANGED",
                        message=f"Attempt {attempt_num} changed root trace_id from '{root_trace_id}' to '{ctx.trace_id}'",
                    )
                )

            # Check valid hex characters in trace_id and span_id
            if not re.fullmatch(r"^[0-9a-fA-F]+$", ctx.trace_id):
                violations.append(
                    TraceViolation(
                        attempt=attempt_num,
                        kind="MALFORMED_HEADER",
                        message=f"Attempt {attempt_num} has malformed non-hex trace_id: '{ctx.trace_id}'",
                    )
                )

            # Check duplicate span IDs on retries (retries must generate distinct spans or child spans)
            if ctx.span_id in seen_span_ids and attempt_num > 1:
                violations.append(
                    TraceViolation(
                        attempt=attempt_num,
                        kind="DUPLICATE_SPAN_ID",
                        message=f"Attempt {attempt_num} re-used duplicate span_id '{ctx.span_id}' without child span nesting",
                    )
                )
            seen_span_ids.add(ctx.span_id)

        passed = len(violations) == 0

        return TraceAuditReport(
            root_trace_id=root_trace_id,
            total_attempts=len(attempts_headers),
            spans_detected=len(spans_summary),
            passed=passed,
            violations=violations,
            format_detected=format_detected,
            spans=spans_summary,
        )


def render_trace_table(report: TraceAuditReport, console: Optional[Console] = None) -> Table:
    """Render Rich visual trace propagation graph and audit results."""
    if console is None:
        console = Console()

    encoding = (getattr(sys.stdout, "encoding", "") or "").lower()
    is_utf8 = "utf" in encoding
    current_box = ROUNDED if is_utf8 else ASCII

    table = Table(
        title=f"🔍 RetryLab Distributed Trace Audit Report (v{__version__})",
        box=current_box,
        expand=True,
        border_style="cyan",
    )
    table.add_column("Property / Check", style="bold cyan", width=26)
    table.add_column("Value / Status", style="bold white", width=34)
    table.add_column("Audit Evaluation", style="white")

    # Root Trace ID
    trace_display = report.root_trace_id or "[italic dim]None[/italic dim]"
    table.add_row(
        "Root Trace ID",
        trace_display,
        f"Format: [bold white]{report.format_detected or 'Unknown'}[/]",
    )

    # Attempts & Spans
    table.add_row(
        "Dispatched Attempts",
        f"{report.total_attempts} attempts | {report.spans_detected} spans",
        "Traced multi-attempt retry sequence across microservices",
    )

    # Overall Verdict
    if report.passed:
        table.add_row(
            "Trace Integrity",
            "[bold green]PASS[/] (Continuity Verified)",
            "Root trace preserved across all retries with distinct span nesting",
        )
    else:
        table.add_row(
            "Trace Integrity",
            f"[bold red]FAIL[/] ({len(report.violations)} violation(s))",
            f"First issue: {report.violations[0].message}",
        )

    # Individual Violations
    for v in report.violations:
        table.add_row(
            f"Attempt #{v.attempt} Violation",
            f"[bold red]{v.kind}[/]",
            v.message,
        )

    return table
