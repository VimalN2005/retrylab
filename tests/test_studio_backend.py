"""
Tests for RetryLab Chaos Studio REST API and Server Engine.
"""

import io
import json
import sys
from unittest.mock import MagicMock
import pytest
import httpx

from retrylab.studio.presets import get_all_presets, get_preset_by_id
from retrylab.studio.server import (
    ChaosStudioHandler,
    create_studio_server,
    start_background_studio,
)


def test_presets_catalog():
    """Verify built-in preset definitions and retrieval."""
    presets = get_all_presets()
    assert len(presets) >= 5

    stripe = get_preset_by_id("stripe_payment_timeout")
    assert stripe is not None
    assert stripe.target == "https://api.stripe.com/v1/charges"
    assert stripe.fault == "timeout"

    openai = get_preset_by_id("openai_rate_limit_429")
    assert openai is not None
    assert openai.status_code == 429

    missing = get_preset_by_id("non_existent_preset")
    assert missing is None


def test_studio_server_binding():
    """Verify studio server instantiates and binds to address."""
    server = create_studio_server("127.0.0.1", 0)
    assert server is not None
    assert server.server_address[0] == "127.0.0.1"
    server.server_close()


def test_studio_handler_run_scenario_logic():
    """Verify in-process execution logic of _handle_run_scenario."""
    handler = ChaosStudioHandler.__new__(ChaosStudioHandler)
    handler.wfile = io.BytesIO()

    sent_data = {}

    def mock_send_json(data, status=200):
        sent_data["data"] = data
        sent_data["status"] = status

    handler._send_json_response = mock_send_json

    run_payload = {
        "name": "stripe_direct_test",
        "target": "https://api.stripe.com/v1/charges",
        "method": "POST",
        "fault": "timeout",
        "fail_count": 1,
        "delay_ms": 10,
    }
    handler._handle_run_scenario(run_payload)

    assert sent_data["status"] == 200
    res = sent_data["data"]
    assert res["status"] == "success"
    assert len(res["timeline"]) == 2
    assert res["timeline"][0]["was_fault_injected"] is True
    assert res["timeline"][1]["was_fault_injected"] is False
    assert res["report"]["recovery_successful"] is True
    assert res["scorecard"]["letter_grade"] == "A+"


def test_studio_handler_export_scenario_logic():
    """Verify multi-language code generation in _handle_export_scenario."""
    handler = ChaosStudioHandler.__new__(ChaosStudioHandler)
    sent_data = {}

    def mock_send_json(data, status=200):
        sent_data["data"] = data
        sent_data["status"] = status

    handler._send_json_response = mock_send_json

    export_payload = {
        "name": "export_test",
        "target": "https://api.openai.com/v1/chat/completions",
        "method": "POST",
        "fault": "http_status",
        "fail_count": 2,
        "status_code": 429,
        "delay_ms": 50,
    }
    handler._handle_export_scenario(export_payload)

    assert sent_data["status"] == 200
    exp = sent_data["data"]
    assert "python" in exp
    assert "go" in exp
    assert "typescript" in exp
    assert "yaml" in exp
    assert "FaultScenario" in exp["python"]
    assert "retrylab.Scenario" in exp["go"]
    assert "Scenario" in exp["typescript"]
    assert "version: 1" in exp["yaml"]


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="Windows sandbox restricts local socket access; runs in Linux CI environment",
)
def test_studio_server_live_e2e():
    """Verify live HTTP communication against background studio server in CI."""
    server, thread = start_background_studio(host="127.0.0.1", port=0)
    port = server.server_address[1]
    base_url = f"http://127.0.0.1:{port}"

    try:
        with httpx.Client(base_url=base_url) as client:
            resp = client.get("/api/health")
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"

            resp = client.get("/api/presets")
            assert resp.status_code == 200
            assert len(resp.json()["presets"]) >= 5
    finally:
        server.shutdown()
        server.server_close()
