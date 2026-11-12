"""
Tests for 'retrylab soak' CLI command.
"""

from __future__ import annotations

import json
from pathlib import Path
from typer.testing import CliRunner

from retrylab.cli.main import app

runner = CliRunner()


def test_soak_cli_table_run():
    """Verify 'retrylab soak' runs quick soak test and prints table output."""
    result = runner.invoke(app, ["soak", "--duration", "0.5", "--concurrency", "2"])
    assert result.exit_code == 0
    assert "Soak & Stress Test Report" in result.stdout
    assert "Storm Amplification Factor" in result.stdout
    assert "Recovery Rate" in result.stdout


def test_soak_cli_json_format():
    """Verify 'retrylab soak --format json' outputs valid JSON structure."""
    result = runner.invoke(app, ["soak", "--duration", "0.5", "--concurrency", "2", "--format", "json"])
    assert result.exit_code == 0

    data = json.loads(result.stdout)
    assert "storm_amplification_factor" in data
    assert "throughput_rps" in data
    assert "latency" in data
    assert "p50_ms" in data["latency"]
    assert "status_distribution" in data
    assert data["concurrency"] == 2


def test_soak_cli_json_out_file(tmp_path: Path):
    """Verify 'retrylab soak --json-out <file>' writes report file to disk."""
    out_file = tmp_path / "soak_report.json"
    result = runner.invoke(app, ["soak", "--duration", "0.4", "--concurrency", "2", "--json-out", str(out_file)])
    assert result.exit_code == 0
    assert out_file.exists()

    data = json.loads(out_file.read_text(encoding="utf-8"))
    assert data["concurrency"] == 2
    assert "storm_severity" in data


def test_soak_cli_invalid_mode():
    """Verify 'retrylab soak --mode bogus' fails with descriptive error."""
    result = runner.invoke(app, ["soak", "--mode", "bogus"])
    assert result.exit_code == 1
    assert "Invalid mode 'bogus'" in result.stdout


def test_soak_cli_storm_threshold_exceeded():
    """Verify 'retrylab soak' exits with code 1 if storm amplification factor exceeds max threshold."""
    # Force failure with impossible max_storm_factor = 0.5 (multiplier is always >= 1.0)
    result = runner.invoke(
        app,
        ["soak", "--duration", "0.5", "--concurrency", "2", "--max-storm-factor", "0.5"],
    )
    assert result.exit_code == 1
    assert "Retry Storm Detected" in result.stdout
