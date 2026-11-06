"""
Tests for RetryLab CLI commands.
"""

import json
from pathlib import Path
import pytest
from typer.testing import CliRunner

from retrylab import __version__
from retrylab.cli.main import app

runner = CliRunner()


def test_cli_version():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert f"RetryLab v{__version__}" in result.stdout


def test_cli_validate_file():
    scenario_path = "examples/scenarios/stripe_outage.yaml"
    result = runner.invoke(app, ["validate", scenario_path])
    assert result.exit_code == 0
    assert "[PASS] Scenario 'stripe_payment_resilience' is valid!" in result.stdout


def test_cli_validate_dir():
    dir_path = "examples/scenarios"
    result = runner.invoke(app, ["validate", dir_path])
    assert result.exit_code == 0
    assert "[PASS] Successfully validated" in result.stdout
    assert "stripe_payment_resilience" in result.stdout


def test_cli_info():
    scenario_path = "examples/scenarios/stripe_outage.yaml"
    result = runner.invoke(app, ["info", scenario_path])
    assert result.exit_code == 0
    assert "Scenario: stripe_payment_resilience" in result.stdout
    assert "Target: https://api.stripe.com/v1/charges" in result.stdout
    assert "Multi-Step Sequential" in result.stdout


def test_cli_drift_detect(tmp_path: Path):
    base_file = tmp_path / "base.json"
    cand_file = tmp_path / "cand.json"

    base_file.write_text(json.dumps({"id": 1, "status": "active"}), encoding="utf-8")
    cand_file.write_text(json.dumps({"id": 2, "status": "active"}), encoding="utf-8")

    result = runner.invoke(app, ["drift", str(base_file), str(cand_file)])
    assert result.exit_code == 0
    assert "[PASS] No schema drift detected" in result.stdout

    # Now introduce drift (missing status)
    cand_file.write_text(json.dumps({"id": 3}), encoding="utf-8")
    fail_result = runner.invoke(app, ["drift", str(base_file), str(cand_file)])
    assert fail_result.exit_code == 1
    assert "[FAIL] Detected 1 schema violation" in fail_result.stdout
