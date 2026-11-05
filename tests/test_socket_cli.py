"""
Tests for CLI 'retrylab socket simulate' commands.
"""

from typer.testing import CliRunner
import pytest

from retrylab.cli.main import app

runner = CliRunner()


def test_cli_socket_help():
    result = runner.invoke(app, ["socket", "--help"])
    assert result.exit_code == 0
    assert "simulate" in result.stdout


def test_cli_socket_simulate_invalid_fault():
    result = runner.invoke(app, ["socket", "simulate", "--fault", "unknown_fault"])
    assert result.exit_code != 0
    assert "Invalid socket fault" in result.stdout


def test_cli_socket_simulate_connection_reset():
    result = runner.invoke(app, ["socket", "simulate", "--fault", "connection_reset"])
    assert result.exit_code == 0
    assert "Simulating Low-Level Socket Fault: CONNECTION_RESET" in result.stdout
    assert "RemoteProtocolError" in result.stdout


def test_cli_socket_simulate_silent_drop():
    result = runner.invoke(app, ["socket", "simulate", "--fault", "silent_drop", "--timeout", "0.02"])
    assert result.exit_code == 0
    assert "Simulating Low-Level Socket Fault: SILENT_DROP" in result.stdout
    assert "ReadTimeout" in result.stdout


def test_cli_socket_simulate_slow_drip():
    result = runner.invoke(app, ["socket", "simulate", "--fault", "slow_drip", "--drip-rate", "16"])
    assert result.exit_code == 0
    assert "Slow Drip Received" in result.stdout
