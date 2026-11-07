"""
Tests for RetryLab Chaos Studio Frontend Assets and CLI Studio Command.
"""

from typer.testing import CliRunner

from retrylab.cli.main import app
from retrylab.studio.assets import render_studio_html

runner = CliRunner()


def test_render_studio_html():
    """Verify HTML template contains required UI components and API scripts."""
    html = render_studio_html()
    assert "<!DOCTYPE html>" in html
    assert "RetryLab Chaos Studio" in html
    assert "/api/run" in html
    assert "/api/presets" in html
    assert "/api/export" in html
    assert "Visual Scenario Builder" in html
    assert "Polyglot SDK Exporter" in html
    assert "codeBlock" in html


def test_cli_studio_help():
    """Verify `retrylab studio --help` displays expected options."""
    result = runner.invoke(app, ["studio", "--help"])
    assert result.exit_code == 0
    assert "Chaos Studio" in result.stdout
    assert "--host" in result.stdout
    assert "--port" in result.stdout
    assert "--open" in result.stdout


def test_cli_ui_alias_help():
    """Verify hidden `retrylab ui` alias functions cleanly."""
    result = runner.invoke(app, ["ui", "--help"])
    assert result.exit_code == 0
    assert "--port" in result.stdout
