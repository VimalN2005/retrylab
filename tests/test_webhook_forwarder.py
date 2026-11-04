"""
Tests for WebhookForwarder and WebhookReplayEngine.
"""

import json
from pathlib import Path
import httpx
import pytest

from retrylab.webhooks import (
    ForwardingResult,
    ForwardingRule,
    ReceivedWebhookEvent,
    WebhookForwarder,
    WebhookReplayEngine,
)


def test_forwarder_basic_success():
    captured_requests = []

    def mock_backend(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        return httpx.Response(200, json={"received": True, "event": request.headers.get("X-Event-Id")})

    client = httpx.Client(transport=httpx.MockTransport(mock_backend))
    rule = ForwardingRule(target_url="http://localhost:8000/api/webhook")
    forwarder = WebhookForwarder(rule=rule, client=client)

    event = ReceivedWebhookEvent(
        event_id="evt_forward_1",
        event_type="payment.succeeded",
        headers={"X-Event-Id": "evt_forward_1", "Stripe-Signature": "t=123,v1=abc"},
        body_raw=b'{"amount": 9900}',
    )

    results = forwarder.forward_event(event)

    assert len(results) == 1
    res = results[0]
    assert res.success is True
    assert res.status_code == 200
    assert res.event_id == "evt_forward_1"
    assert res.attempt == 1

    assert len(captured_requests) == 1
    assert captured_requests[0].headers["X-Event-Id"] == "evt_forward_1"
    assert captured_requests[0].headers["Stripe-Signature"] == "t=123,v1=abc"
    assert len(forwarder.history) == 1


def test_forwarder_duplicate_and_delay():
    captured_requests = []

    def mock_backend(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        return httpx.Response(200, json={"status": "ok"})

    client = httpx.Client(transport=httpx.MockTransport(mock_backend))
    rule = ForwardingRule(
        target_url="http://localhost:8000/api/webhook",
        duplicate_count=3,
        inject_delay_seconds=0.01,
    )
    forwarder = WebhookForwarder(rule=rule, client=client)

    event = ReceivedWebhookEvent(
        event_id="evt_dup_forward",
        event_type="order.placed",
        headers={"X-Event-Id": "evt_dup_forward"},
        body_raw=b'{"order_id": 42}',
    )

    results = forwarder.forward_event(event)
    assert len(results) == 3
    for idx, r in enumerate(results, 1):
        assert r.attempt == idx
        assert r.success is True
    assert len(captured_requests) == 3


def test_forwarder_strip_signature():
    captured_headers = []

    def mock_backend(request: httpx.Request) -> httpx.Response:
        captured_headers.append(dict(request.headers))
        return httpx.Response(200, json={"ok": True})

    client = httpx.Client(transport=httpx.MockTransport(mock_backend))
    rule = ForwardingRule(
        target_url="http://localhost:8000/api/webhook",
        strip_signature=True,
    )
    forwarder = WebhookForwarder(rule=rule, client=client)

    event = ReceivedWebhookEvent(
        event_id="evt_strip",
        headers={"Stripe-Signature": "t=1,v1=x", "X-Custom": "retain_me"},
        body_raw=b'{"data": 1}',
    )

    results = forwarder.forward_event(event)
    assert results[0].success is True
    headers = captured_headers[0]
    assert "stripe-signature" not in headers
    assert "x-custom" in headers


def test_replay_engine_events():
    received_event_ids = []

    def mock_backend(request: httpx.Request) -> httpx.Response:
        received_event_ids.append(request.headers.get("X-Event-Id"))
        return httpx.Response(200, json={"replayed": True})

    client = httpx.Client(transport=httpx.MockTransport(mock_backend))
    engine = WebhookReplayEngine(client=client)

    events = [
        ReceivedWebhookEvent(event_id="evt_step_1", headers={"X-Event-Id": "evt_step_1"}, body_raw=b"{}"),
        ReceivedWebhookEvent(event_id="evt_step_2", headers={"X-Event-Id": "evt_step_2"}, body_raw=b"{}"),
        ReceivedWebhookEvent(event_id="evt_step_3", headers={"X-Event-Id": "evt_step_3"}, body_raw=b"{}"),
    ]

    # 1. Forward order
    res = engine.replay_events(events, target_url="http://test/replay", delay_between_events=0.0)
    assert len(res) == 3
    assert received_event_ids == ["evt_step_1", "evt_step_2", "evt_step_3"]

    # 2. Reverse order
    received_event_ids.clear()
    res_rev = engine.replay_events(events, target_url="http://test/replay", reverse_order=True)
    assert len(res_rev) == 3
    assert received_event_ids == ["evt_step_3", "evt_step_2", "evt_step_1"]


def test_replay_engine_file_fixture(tmp_path: Path):
    fixture_file = tmp_path / "webhooks_recorded.json"
    data = [
        {"event_id": "evt_json_1", "event_type": "user.signup", "body_raw": "{}", "headers": {"X-Event-Id": "evt_json_1"}},
        {"event_id": "evt_json_2", "event_type": "user.verified", "body_raw": "{}", "headers": {"X-Event-Id": "evt_json_2"}},
    ]
    fixture_file.write_text(json.dumps(data), encoding="utf-8")

    def mock_backend(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})

    client = httpx.Client(transport=httpx.MockTransport(mock_backend))
    engine = WebhookReplayEngine(client=client)

    loaded = engine.load_fixture_file(fixture_file)
    assert len(loaded) == 2
    assert loaded[0].event_id == "evt_json_1"

    res = engine.replay_events(loaded, target_url="http://test/replay")
    assert len(res) == 2
    assert all(r.success for r in res)
