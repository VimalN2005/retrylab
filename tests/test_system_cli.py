"""
Unit tests for 'retrylab system' and 'retrylab version' CLI commands.
"""

import json
from typer.testing import CliRunner

from retrylab import __version__
from retrylab.cli.main import app

runner = CliRunner()


def test_cli_version_basic():
    """Verify 'retrylab version' outputs current version string."""
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert f"RetryLab v{__version__}" in result.stdout
    assert "0.3.0-alpha.1" in result.stdout


def test_cli_version_verbose():
    """Verify 'retrylab version --verbose' delegates to system capabilities matrix."""
    result = runner.invoke(app, ["version", "--verbose"])
    assert result.exit_code == 0
    assert "System & Capabilities Matrix" in result.stdout
    assert "Polyglot SDKs" in result.stdout
    assert "v0.3.0-alpha.1" in result.stdout


def test_cli_system_table():
    """Verify 'retrylab system' renders Rich capabilities table."""
    result = runner.invoke(app, ["system"])
    assert result.exit_code == 0
    assert "Capabilities Matrix" in result.stdout
    assert "Phase 3 Grand Release" in result.stdout
    assert "HTTP/2 & gRPC" in result.stdout


def test_cli_system_json():
    """Verify 'retrylab system --format json' outputs valid JSON structure."""
    result = runner.invoke(app, ["system", "--format", "json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["product"] == "RetryLab"
    assert data["version"] == f"v{__version__}"
    assert "python" in data["sdks"]
    assert "go" in data["sdks"]
    assert "typescript" in data["sdks"]
    assert len(data["protocols"]) >= 5
    assert len(data["auditors"]) >= 4
