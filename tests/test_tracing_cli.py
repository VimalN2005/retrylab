"""
Tests for 'retrylab trace' CLI command.
"""

from __future__ import annotations

import json
from typer.testing import CliRunner

from retrylab.cli.main import app

runner = CliRunner()


def test_trace_cli_generate_w3c():
    """Verify 'retrylab trace generate --format w3c' prints trace table with traceparent."""
    result = runner.invoke(app, ["trace", "generate", "--format", "w3c"])
    assert result.exit_code == 0
    assert "Generated Distributed Trace Context" in result.stdout
    assert "W3C" in result.stdout
    assert "Header: traceparent" in result.stdout
    assert "PASS" in result.stdout


def test_trace_cli_generate_json():
    """Verify 'retrylab trace generate --output json' outputs valid JSON context."""
    result = runner.invoke(app, ["trace", "generate", "--format", "b3", "--output", "json"])
    assert result.exit_code == 0

    data = json.loads(result.stdout)
    assert data["format"] == "b3_single"
    assert "trace_id" in data
    assert "span_id" in data
    assert "b3" in data["headers"]


def test_trace_cli_generate_corrupt():
    """Verify 'retrylab trace generate --corrupt' injects malformed trace ID."""
    result = runner.invoke(app, ["trace", "generate", "--corrupt"])
    assert result.exit_code == 0
    assert "CHAOS INJECTED" in result.stdout


def test_trace_cli_simulate_clean():
    """Verify 'retrylab trace simulate --hops 3' validates 3-attempt span continuity."""
    result = runner.invoke(app, ["trace", "simulate", "--hops", "3"])
    assert result.exit_code == 0
    assert "Distributed Trace Audit Report" in result.stdout
    assert "Trace Integrity" in result.stdout
    assert "Distributed Trace Integrity Verified" in result.stdout
    assert "3 spans tracked" in result.stdout


def test_trace_cli_simulate_json():
    """Verify 'retrylab trace simulate --output json' outputs structured TraceAuditReport."""
    result = runner.invoke(app, ["trace", "simulate", "--hops", "2", "--output", "json"])
    assert result.exit_code == 0

    data = json.loads(result.stdout)
    assert data["passed"] is True
    assert data["total_attempts"] == 2
    assert data["spans_detected"] == 2
    assert "root_trace_id" in data


def test_trace_cli_simulate_corrupt_fails():
    """Verify 'retrylab trace simulate --corrupt' catches trace corruption and exits with 1."""
    result = runner.invoke(app, ["trace", "simulate", "--corrupt"])
    assert result.exit_code == 1
    assert "Trace Propagation Broken" in result.stdout


def test_trace_cli_invalid_format():
    """Verify 'retrylab trace generate --format bogus' fails with descriptive error."""
    result = runner.invoke(app, ["trace", "generate", "--format", "bogus"])
    assert result.exit_code == 1
    assert "Invalid format 'bogus'" in result.stdout


def test_trace_cli_invalid_action():
    """Verify 'retrylab trace unknown_action' fails with error code 1."""
    result = runner.invoke(app, ["trace", "unknown_action"])
    assert result.exit_code == 1
    assert "Unknown action 'unknown_action'" in result.stdout
