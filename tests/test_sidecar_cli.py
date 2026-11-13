"""
Tests for 'retrylab sidecar' CLI command.
"""

from __future__ import annotations

import json
from pathlib import Path
from typer.testing import CliRunner

from retrylab.cli.main import app

runner = CliRunner()


def test_sidecar_cli_help():
    """Verify 'retrylab sidecar --help' displays options and usage information."""
    result = runner.invoke(app, ["sidecar", "--help"])
    assert result.exit_code == 0
    assert "Launch zero-code containerized chaos sidecar" in result.stdout
    assert "--port" in result.stdout
    assert "--host" in result.stdout
    assert "--scenario" in result.stdout
    assert "--target" in result.stdout
    assert "--daemon" in result.stdout


def test_sidecar_cli_invalid_port():
    """Verify 'retrylab sidecar --port 99999' fails with error code 1."""
    result = runner.invoke(app, ["sidecar", "--port", "99999"])
    assert result.exit_code == 1
    assert "Invalid port '99999'" in result.stdout


def test_sidecar_cli_missing_scenario_file():
    """Verify 'retrylab sidecar --scenario nonexistent.yaml' fails gracefully."""
    result = runner.invoke(app, ["sidecar", "--scenario", "nonexistent_file_xyz.yaml"])
    assert result.exit_code == 1
    assert "Scenario file not found" in result.stdout


def test_sidecar_cli_json_format_meta():
    """Verify 'retrylab sidecar --format json' outputs valid endpoint metadata."""
    result = runner.invoke(app, ["sidecar", "--format", "json", "--port", "8089", "--target", "https://api.stripe.com"])
    assert result.exit_code == 0

    data = json.loads(result.stdout)
    assert data["port"] == 8089
    assert data["target"] == "https://api.stripe.com"
    assert "endpoints" in data
    assert "health" in data["endpoints"]
    assert "metrics" in data["endpoints"]


def test_sidecar_cli_daemon_mode_with_scenario(tmp_path: Path):
    """Verify 'retrylab sidecar --daemon' initializes cleanly with scenario file."""
    yaml_content = """
name: test_cli_sidecar
target: "*/v1/test*"
fault: rate_limit_429
fail_count: 1
"""
    sc_file = tmp_path / "test_sidecar.yaml"
    sc_file.write_text(yaml_content, encoding="utf-8")

    result = runner.invoke(app, ["sidecar", "--scenario", str(sc_file), "--daemon", "--port", "0", "--format", "json"])
    assert result.exit_code == 0

    data = json.loads(result.stdout)
    assert data["scenario"] == "test_cli_sidecar"
