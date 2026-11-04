"""
Tests for CLI 'retrylab webhook listen' and 'retrylab webhook replay'.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from typer.testing import CliRunner

from retrylab.cli.main import app

runner = CliRunner()


def test_cli_webhook_listen_help():
    result = runner.invoke(app, ["webhook", "listen", "--help"])
    assert result.exit_code == 0
    assert "--forward-to" in result.stdout
    assert "--fail-first" in result.stdout
    assert "--port" in result.stdout


def test_cli_webhook_replay_help():
    result = runner.invoke(app, ["webhook", "replay", "--help"])
    assert result.exit_code == 0
    assert "--target" in result.stdout
    assert "--interval" in result.stdout
    assert "--reverse" in result.stdout


def test_cli_webhook_replay_file_not_found():
    result = runner.invoke(app, ["webhook", "replay", "non_existent_file.json", "--target", "http://localhost:8000"])
    assert result.exit_code != 0
    assert "Fixture file not found" in result.stdout


def test_cli_webhook_replay_success(tmp_path: Path):
    fixture_file = tmp_path / "events.json"
    data = [
        {"event_id": "evt_cli_1", "event_type": "test.ping", "body_raw": "{}", "headers": {}},
        {"event_id": "evt_cli_2", "event_type": "test.pong", "body_raw": "{}", "headers": {}},
    ]
    fixture_file.write_text(json.dumps(data), encoding="utf-8")

    from retrylab.webhooks import ForwardingResult

    fake_results = [
        ForwardingResult(event_id="evt_cli_1", event_type="test.ping", target_url="http://test/hook", status_code=200, latency_ms=5.0, attempt=1, success=True),
        ForwardingResult(event_id="evt_cli_2", event_type="test.pong", target_url="http://test/hook", status_code=200, latency_ms=6.0, attempt=1, success=True),
    ]

    with patch("retrylab.cli.main.WebhookReplayEngine.replay_events", return_value=fake_results):
        result = runner.invoke(app, ["webhook", "replay", str(fixture_file), "--target", "http://test/hook"])
        assert result.exit_code == 0
        assert "Replaying 2 webhook event(s)" in result.stdout
        assert "Replay Complete: 2/2 delivered successfully" in result.stdout
