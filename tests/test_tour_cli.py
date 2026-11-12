"""
Tests for 'retrylab tour' CLI command.
"""

from __future__ import annotations

import json
from typer.testing import CliRunner

from retrylab.cli.main import app

runner = CliRunner()


def test_tour_cli_auto_full_run():
    """Verify 'retrylab tour --auto' executes all 5 lessons without prompting."""
    result = runner.invoke(app, ["tour", "--auto", "--speed", "10.0"])
    assert result.exit_code == 0
    assert "RetryLab Resilience Tour" in result.stdout
    assert "Stop 1 of 5" in result.stdout
    assert "Stop 5 of 5" in result.stdout
    assert "Tour Completion Scorecard" in result.stdout
    assert "Resilience Tour Completed: 5 lesson(s) verified" in result.stdout


def test_tour_cli_single_step():
    """Verify 'retrylab tour --step 2 --auto' executes only target lesson."""
    result = runner.invoke(app, ["tour", "--auto", "--step", "2", "--speed", "10.0"])
    assert result.exit_code == 0
    assert "Stop 2 of 5" in result.stdout
    assert "Cryptographic Idempotency Shield" in result.stdout
    assert "Resilience Tour Completed: 1 lesson(s) verified" in result.stdout


def test_tour_cli_invalid_step():
    """Verify 'retrylab tour --step 9' exits with error code 1."""
    result = runner.invoke(app, ["tour", "--step", "9"])
    assert result.exit_code == 1
    assert "Invalid step '9'" in result.stdout


def test_tour_cli_json_all_steps():
    """Verify 'retrylab tour --format json' outputs structured catalog of all steps."""
    result = runner.invoke(app, ["tour", "--format", "json"])
    assert result.exit_code == 0

    data = json.loads(result.stdout)
    assert "steps" in data
    assert len(data["steps"]) == 5
    assert data["steps"][0]["id"] == "rate_limit_recovery"
    assert data["steps"][4]["id"] == "storm_amplification"


def test_tour_cli_json_single_step():
    """Verify 'retrylab tour --step 3 --format json' outputs single step details."""
    result = runner.invoke(app, ["tour", "--step", "3", "--format", "json"])
    assert result.exit_code == 0

    data = json.loads(result.stdout)
    assert data["step_number"] == 3
    assert data["id"] == "streaming_chaos"
    assert "StreamingChaosConfig" in data["code_example"]
