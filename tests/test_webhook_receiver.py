"""
Tests for MockWebhookReceiver, in-process fault simulation, and signature verification.
"""

import time
import httpx
import pytest

from retrylab.webhooks import (
    MockWebhookReceiver,
    WebhookEmitter,
    WebhookEvent,
    WebhookReceiverFaultConfig,
    WebhookSignatureScheme,
    compute_webhook_signature,
    verify_webhook_signature,
)


def test_mock_webhook_receiver_basic():
    secret = "whsec_test_secret_abc"
    receiver = MockWebhookReceiver(
        secret=secret,
        scheme=WebhookSignatureScheme.STRIPE_V1,
    )

    client = httpx.Client(transport=receiver.as_transport())
    emitter = WebhookEmitter(
        target_url="http://mock-receiver/webhooks",
        secret=secret,
        scheme=WebhookSignatureScheme.STRIPE_V1,
        client=client,
    )

    event = WebhookEvent(
        event_id="evt_charge_12345",
        event_type="charge.succeeded",
        payload={"amount": 4200, "currency": "usd"},
    )

    resp = emitter.dispatch(event)
    assert resp.status_code == 200
    assert resp.json()["received"] is True

    assert receiver.request_count == 1
    events = receiver.events
    assert len(events) == 1
    evt = events[0]
    assert evt.event_id == "evt_charge_12345"
    assert evt.event_type == "charge.succeeded"
    assert evt.payload == {"amount": 4200, "currency": "usd"}
    assert evt.signature_valid is True
    assert evt.response_status == 200

    receiver.assert_event_received("charge.succeeded", count=1)
    receiver.assert_all_signatures_valid()


def test_mock_webhook_receiver_signature_rejection():
    secret = "whsec_real_secret"
    receiver = MockWebhookReceiver(
        secret=secret,
        scheme=WebhookSignatureScheme.STRIPE_V1,
        fault_config=WebhookReceiverFaultConfig(reject_invalid_signatures=True),
    )

    client = httpx.Client(transport=receiver.as_transport())
    # Emitter configured with wrong/tampered secret
    tampered_emitter = WebhookEmitter(
        target_url="http://mock-receiver/webhooks",
        secret="whsec_forged_secret",
        scheme=WebhookSignatureScheme.STRIPE_V1,
        client=client,
    )

    event = WebhookEvent(
        event_id="evt_tampered",
        event_type="customer.created",
        payload={"name": "Alice"},
    )

    resp = tampered_emitter.dispatch(event)
    assert resp.status_code == 401
    assert "Invalid signature" in resp.json()["error"]

    assert receiver.request_count == 1
    evt = receiver.events[0]
    assert evt.signature_valid is False
    assert evt.response_status == 401


def test_mock_webhook_receiver_fail_first_n():
    secret = "whsec_retry_test"
    receiver = MockWebhookReceiver(
        secret=secret,
        scheme=WebhookSignatureScheme.STRIPE_V1,
        fault_config=WebhookReceiverFaultConfig(
            fail_first_n=2,
            fail_status_code=503,
            fail_response_body={"error": "Database connection pool saturated"},
        ),
    )

    client = httpx.Client(transport=receiver.as_transport())
    emitter = WebhookEmitter(
        target_url="http://mock-receiver/webhooks",
        secret=secret,
        scheme=WebhookSignatureScheme.STRIPE_V1,
        client=client,
    )

    event = WebhookEvent(
        event_id="evt_retry_flow",
        event_type="invoice.payment_succeeded",
        payload={"invoice": "in_999"},
    )

    # Attempt 1: Injected 503
    r1 = emitter.dispatch(event)
    assert r1.status_code == 503
    assert "Database connection pool" in r1.json()["error"]

    # Attempt 2: Injected 503
    r2 = emitter.dispatch(event)
    assert r2.status_code == 503

    # Attempt 3: Recovers cleanly to 200
    r3 = emitter.dispatch(event)
    assert r3.status_code == 200
    assert r3.json()["received"] is True

    assert receiver.request_count == 3
    assert len(receiver.events) == 3
    assert receiver.events[0].response_status == 503
    assert receiver.events[1].response_status == 503
    assert receiver.events[2].response_status == 200


def test_mock_webhook_receiver_delay():
    receiver = MockWebhookReceiver(
        fault_config=WebhookReceiverFaultConfig(delay_seconds=0.05),
    )
    client = httpx.Client(transport=receiver.as_transport())

    t0 = time.time()
    resp = client.post("http://mock-receiver/webhooks", json={"ping": "pong"})
    elapsed = time.time() - t0

    assert resp.status_code == 200
    assert elapsed >= 0.04


def test_mock_webhook_receiver_queries_and_clear():
    receiver = MockWebhookReceiver()
    client = httpx.Client(transport=receiver.as_transport())

    client.post("http://mock-receiver/webhooks", json={"type": "order.created", "id": "ord_1"})
    client.post("http://mock-receiver/webhooks", json={"type": "order.paid", "id": "ord_2"})
    client.post("http://mock-receiver/webhooks", json={"type": "order.created", "id": "ord_3"})

    assert receiver.request_count == 3
    assert len(receiver.get_events_by_type("order.created")) == 2
    assert len(receiver.get_events_by_type("order.paid")) == 1
    assert receiver.get_event_by_id("ord_2") is not None
    assert receiver.get_event_by_id("ord_999") is None

    receiver.clear()
    assert receiver.request_count == 0
    assert len(receiver.events) == 0


def test_verify_signatures_github_and_hmac():
    secret = "gh_and_hmac_secret"
    body = b'{"ref":"refs/heads/main"}'

    # 1. GitHub SHA-256
    gh_headers, _ = compute_webhook_signature(body, secret, WebhookSignatureScheme.GITHUB_SHA256)
    valid_gh, msg = verify_webhook_signature(gh_headers, body, secret, WebhookSignatureScheme.GITHUB_SHA256)
    assert valid_gh is True

    # Tampered GitHub signature
    invalid_gh, _ = verify_webhook_signature({"X-Hub-Signature-256": "sha256=badbadbad"}, body, secret, WebhookSignatureScheme.GITHUB_SHA256)
    assert invalid_gh is False

    # 2. Generic HMAC SHA-256
    hmac_headers, _ = compute_webhook_signature(body, secret, WebhookSignatureScheme.HMAC_SHA256)
    valid_hmac, _ = verify_webhook_signature(hmac_headers, body, secret, WebhookSignatureScheme.HMAC_SHA256)
    assert valid_hmac is True
