"""
Tests for TrafficRecorder and ReplayTransport.
"""

import json
from pathlib import Path
import httpx
import pytest

from retrylab import (
    FaultScenario,
    FaultType,
    RecordedInteraction,
    ReplayTransport,
    TrafficRecorder,
)


def test_traffic_recorder_redaction_and_persistence(tmp_path: Path):
    recorder = TrafficRecorder()

    req = httpx.Request(
        "POST",
        "https://api.stripe.com/v1/charges",
        headers={"Authorization": "Bearer rk_live_supersecrettoken", "Content-Type": "application/json"},
        content=b'{"amount": 5000, "card_number": "4111111111111234"}',
    )
    resp = httpx.Response(
        status_code=200,
        headers={"Content-Type": "application/json", "Set-Cookie": "session=xyz"},
        content=b'{"id": "ch_9999", "status": "paid"}',
        request=req,
    )

    interaction = recorder.record(req, resp)

    # Verify sensitive data was redacted before storing
    auth_val = interaction.request_headers.get("authorization") or interaction.request_headers.get("Authorization")
    assert auth_val == "[REDACTED]"

    cookie_val = interaction.response_headers.get("set-cookie") or interaction.response_headers.get("Set-Cookie")
    assert cookie_val == "[REDACTED]"
    assert "[REDACTED]" in interaction.request_body

    # Save to disk
    fixture_path = tmp_path / "stripe_charge.json"
    recorder.save(fixture_path)
    assert fixture_path.exists()

    # Load back
    loaded = TrafficRecorder.load(fixture_path)
    assert len(loaded) == 1
    assert loaded[0].url == "https://api.stripe.com/v1/charges"
    assert loaded[0].status_code == 200


def test_replay_transport_offline():
    interactions = [
        RecordedInteraction(
            url="https://api.openai.com/v1/models",
            method="GET",
            response_headers={"Content-Type": "application/json"},
            response_body=json.dumps({"data": [{"id": "gpt-4o"}]}),
            status_code=200,
        )
    ]
    transport = ReplayTransport(interactions=interactions)

    with httpx.Client(transport=transport) as client:
        # 1. Matching request returns recorded fixture
        resp = client.get("https://api.openai.com/v1/models")
        assert resp.status_code == 200
        assert resp.json()["data"][0]["id"] == "gpt-4o"

        # 2. Unmatched request returns 404
        unmatched = client.get("https://api.openai.com/v1/unknown")
        assert unmatched.status_code == 404


def test_replay_transport_with_fault_injection():
    # Demonstrates fault injection ON TOP of recorded baseline fixtures
    interactions = [
        RecordedInteraction(
            url="https://api.stripe.com/v1/charges",
            method="POST",
            response_headers={"Content-Type": "application/json"},
            response_body='{"status": "succeeded", "charge_id": "ch_rec_123"}',
            status_code=200,
        )
    ]
    scenario = FaultScenario(
        target="https://api.stripe.com/v1/charges",
        fault=FaultType.TIMEOUT,
        fail_count=1,
    )
    transport = ReplayTransport(interactions=interactions, scenario=scenario)

    with httpx.Client(transport=transport) as client:
        # Attempt 1: Injected timeout
        with pytest.raises(httpx.ReadTimeout):
            client.post("https://api.stripe.com/v1/charges")

        # Attempt 2: Recovers and replays the recorded fixture!
        resp2 = client.post("https://api.stripe.com/v1/charges")
        assert resp2.status_code == 200
        assert resp2.json()["charge_id"] == "ch_rec_123"
