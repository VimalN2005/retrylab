"""
Tests for CI Reliability Gate command and report output.
"""

from pathlib import Path
from typer.testing import CliRunner

from retrylab.cli.main import app

runner = CliRunner()


def test_cli_gate_execution(tmp_path: Path):
    scenario_file = "examples/scenarios/stripe_outage.yaml"
    report_file = tmp_path / "ci_summary.md"

    result = runner.invoke(app, ["gate", scenario_file, "--report", str(report_file)])
    assert result.exit_code == 0
    assert "[PASS] Reliability Gate Passed: stripe_payment_resilience" in result.stdout
    assert report_file.exists()

    content = report_file.read_text(encoding="utf-8")
    assert "# 🧪 RetryLab Reliability Report" in content
    assert "stripe_payment_resilience" in content
    assert "🟢 PASS" in content
