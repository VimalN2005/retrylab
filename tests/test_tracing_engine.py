"""
Tests for RetryLab Distributed Tracing & OpenTelemetry Engine (retrylab.tracing).
"""

from __future__ import annotations

from rich.table import Table

from retrylab.tracing import (
    TraceAuditReport,
    TraceAuditor,
    TraceContext,
    TraceFormat,
    TraceViolation,
    render_trace_table,
)


def test_w3c_traceparent_serialization_and_parsing():
    """Verify W3C TraceContext generation, header formatting, and bidirectional parsing."""
    ctx = TraceContext.generate(format=TraceFormat.W3C_TRACECONTEXT, sampled=True)
    headers = ctx.to_headers()
    assert "traceparent" in headers

    tp = headers["traceparent"]
    assert tp.startswith("00-")
    assert tp.endswith("-01")
    assert len(ctx.trace_id) == 32
    assert len(ctx.span_id) == 16

    parsed = TraceContext.from_headers(headers)
    assert parsed is not None
    assert parsed.trace_id == ctx.trace_id
    assert parsed.span_id == ctx.span_id
    assert parsed.sampled is True
    assert parsed.format == TraceFormat.W3C_TRACECONTEXT


def test_b3_single_and_multi_format():
    """Verify B3 single-header and multi-header serialization and parsing."""
    # B3 Single
    ctx_b3_single = TraceContext.generate(format=TraceFormat.B3_SINGLE, sampled=True)
    hdrs_single = ctx_b3_single.to_headers()
    assert "b3" in hdrs_single
    parsed_single = TraceContext.from_headers(hdrs_single)
    assert parsed_single is not None
    assert parsed_single.trace_id == ctx_b3_single.trace_id
    assert parsed_single.span_id == ctx_b3_single.span_id

    # B3 Multi
    ctx_b3_multi = TraceContext.generate(format=TraceFormat.B3_MULTI, sampled=False)
    hdrs_multi = ctx_b3_multi.to_headers()
    assert "X-B3-TraceId" in hdrs_multi
    assert "X-B3-SpanId" in hdrs_multi
    assert hdrs_multi["X-B3-Sampled"] == "0"

    parsed_multi = TraceContext.from_headers(hdrs_multi)
    assert parsed_multi is not None
    assert parsed_multi.trace_id == ctx_b3_multi.trace_id
    assert parsed_multi.sampled is False


def test_aws_xray_and_datadog_formats():
    """Verify AWS X-Ray and Datadog trace header support."""
    # AWS X-Ray
    ctx_xray = TraceContext.generate(format=TraceFormat.AWS_XRAY, sampled=True)
    hdrs_xray = ctx_xray.to_headers()
    assert "X-Amzn-Trace-Id" in hdrs_xray
    assert "Root=1-" in hdrs_xray["X-Amzn-Trace-Id"]

    parsed_xray = TraceContext.from_headers(hdrs_xray)
    assert parsed_xray is not None
    assert parsed_xray.sampled is True

    # Datadog
    ctx_dd = TraceContext.generate(format=TraceFormat.DATADOG, sampled=True)
    hdrs_dd = ctx_dd.to_headers()
    assert "x-datadog-trace-id" in hdrs_dd
    assert "x-datadog-parent-id" in hdrs_dd
    parsed_dd = TraceContext.from_headers(hdrs_dd)
    assert parsed_dd is not None
    assert parsed_dd.sampled is True


def test_child_span_creation_and_parent_linkage():
    """Verify child span inherits root trace_id and records parent_span_id."""
    parent = TraceContext.generate(format=TraceFormat.W3C_TRACECONTEXT)
    child = parent.create_child_span()

    assert child.trace_id == parent.trace_id
    assert child.span_id != parent.span_id
    assert child.parent_span_id == parent.span_id
    assert child.sampled == parent.sampled


def test_corrupt_trace_id_injection():
    """Verify injecting malformed characters into trace ID."""
    ctx = TraceContext.generate()
    corrupted = ctx.corrupt_trace_id()
    assert corrupted.trace_id.startswith("ZZ")


def test_trace_auditor_clean_retry_sequence():
    """Verify clean 3-attempt retry sequence passes trace integrity audit."""
    parent = TraceContext.generate()
    attempt1 = parent.create_child_span()
    attempt2 = parent.create_child_span()
    attempt3 = parent.create_child_span()

    attempts = [attempt1.to_headers(), attempt2.to_headers(), attempt3.to_headers()]

    auditor = TraceAuditor()
    report = auditor.audit_trace_sequence(attempts)

    assert report.passed is True
    assert report.total_attempts == 3
    assert report.spans_detected == 3
    assert report.root_trace_id == parent.trace_id
    assert len(report.violations) == 0


def test_trace_auditor_detects_changed_trace_id():
    """Verify auditor catches trace ID changes between retry attempts."""
    ctx1 = TraceContext.generate()
    ctx2 = TraceContext.generate()  # Accidentally new trace ID on retry!

    auditor = TraceAuditor()
    report = auditor.audit_trace_sequence([ctx1.to_headers(), ctx2.to_headers()])

    assert report.passed is False
    assert len(report.violations) >= 1
    assert any(v.kind == "TRACE_ID_CHANGED" for v in report.violations)


def test_trace_auditor_detects_dropped_trace_headers():
    """Verify auditor catches retries that fail to propagate trace context."""
    ctx1 = TraceContext.generate()
    empty_headers = {"User-Agent": "retrylab/1.0"}

    auditor = TraceAuditor()
    report = auditor.audit_trace_sequence([ctx1.to_headers(), empty_headers])

    assert report.passed is False
    assert any(v.kind == "MISSING_HEADER" for v in report.violations)


def test_trace_auditor_detects_duplicate_span_id():
    """Verify auditor detects duplicate span_id re-used across retries."""
    ctx = TraceContext.generate()
    # Attempt 1 and Attempt 2 send exact same span_id without child nesting
    attempts = [ctx.to_headers(), ctx.to_headers()]

    auditor = TraceAuditor()
    report = auditor.audit_trace_sequence(attempts)

    assert report.passed is False
    assert any(v.kind == "DUPLICATE_SPAN_ID" for v in report.violations)


def test_render_trace_table_visualization():
    """Verify Rich visual table generation for TraceAuditReport."""
    ctx = TraceContext.generate()
    auditor = TraceAuditor()
    report = auditor.audit_trace_sequence([ctx.to_headers()])
    table = render_trace_table(report)

    assert isinstance(table, Table)
    assert "Distributed Trace Audit Report" in str(table.title)
    assert len(table.rows) >= 3
