"""
Tests for ChaosWebhookDispatcher (duplicate, out-of-order, signature tampering, clock skew).
"""

import time
import httpx
import pytest

from retrylab.webhooks import (
    ChaosWebhookConfig,
    ChaosWebhookDispatcher,
    WebhookChaosMode,
    WebhookEmitter,
    WebhookEvent,
    WebhookSignatureScheme,
)


@pytest.fixture
def mock_receiver():
    received_requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        received_requests.append(request)
        return httpx.Response(status_code=200, json={"received": True, "path": str(request.url)})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return client, received_requests


def test_chaos_duplicate_dispatch(mock_receiver):
    client, received = mock_receiver
    emitter = WebhookEmitter(
        target_url="http://testserver/webhook",
        secret="whsec_secret_123",
        scheme=WebhookSignatureScheme.STRIPE_V1,
        client=client,
    )
    dispatcher = ChaosWebhookDispatcher(emitter)

    event = WebhookEvent(
        event_id="evt_duplicate_001",
        event_type="invoice.payment_succeeded",
        payload={"invoice_id": "inv_123", "amount": 5000},
    )

    config = ChaosWebhookConfig(
        mode=WebhookChaosMode.DUPLICATE,
        duplicate_count=3,
    )

    results = dispatcher.dispatch_with_chaos(event, config)

    assert len(results) == 3
    assert len(received) == 3
    for r in results:
        assert r.event_id == "evt_duplicate_001"
        assert r.status_code == 200
        assert r.chaos_mode == WebhookChaosMode.DUPLICATE

    for req in received:
        assert req.headers["X-Event-Id"] == "evt_duplicate_001"


def test_chaos_out_of_order_batch(mock_receiver):
    client, received = mock_receiver
    emitter = WebhookEmitter(
        target_url="http://testserver/webhook",
        secret="whsec_secret_order",
        scheme=WebhookSignatureScheme.GITHUB_SHA256,
        client=client,
    )
    dispatcher = ChaosWebhookDispatcher(emitter)

    events = [
        WebhookEvent(event_id="evt_step_1", event_type="order.created", payload={"step": 1}),
        WebhookEvent(event_id="evt_step_2", event_type="order.paid", payload={"step": 2}),
        WebhookEvent(event_id="evt_step_3", event_type="order.shipped", payload={"step": 3}),
    ]

    config = ChaosWebhookConfig(mode=WebhookChaosMode.OUT_OF_ORDER)
    results = dispatcher.dispatch_batch(events, config)

    assert len(results) == 3
    # Verify delivery order was inverted
    assert results[0].event_id == "evt_step_3"
    assert results[1].event_id == "evt_step_2"
    assert results[2].event_id == "evt_step_1"

    assert received[0].headers["X-Event-Id"] == "evt_step_3"
    assert received[1].headers["X-Event-Id"] == "evt_step_2"
    assert received[2].headers["X-Event-Id"] == "evt_step_1"


def test_chaos_invalid_signature():
    # Mock server that verifies Stripe HMAC signatures
    secret = "real_secret_key_456"

    def verifying_handler(request: httpx.Request) -> httpx.Response:
        sig_header = request.headers.get("Stripe-Signature", "")
        # Expect signature to match real secret
        import hmac, hashlib
        # Extract t and v1
        parts = dict(kv.split("=", 1) for kv in sig_header.split(","))
        ts = parts.get("t", "")
        v1 = parts.get("v1", "")
        expected = hmac.new(
            secret.encode(),
            f"{ts}.".encode() + request.content,
            hashlib.sha256,
        ).hexdigest()

        if hmac.compare_digest(v1, expected):
            return httpx.Response(status_code=200, json={"verified": True})
        return httpx.Response(status_code=401, json={"error": "Invalid signature"})

    client = httpx.Client(transport=httpx.MockTransport(verifying_handler))
    emitter = WebhookEmitter(
        target_url="http://testserver/webhook",
        secret=secret,
        scheme=WebhookSignatureScheme.STRIPE_V1,
        client=client,
    )
    dispatcher = ChaosWebhookDispatcher(emitter)

    event = WebhookEvent(
        event_id="evt_sig_test",
        event_type="charge.captured",
        payload={"id": "ch_789"},
    )

    # 1. Dispatch normal - should succeed
    normal_res = dispatcher.dispatch_with_chaos(event, ChaosWebhookConfig(mode=WebhookChaosMode.NONE))
    assert normal_res[0].status_code == 200

    # 2. Dispatch with invalid signature - should be rejected with 401
    chaos_res = dispatcher.dispatch_with_chaos(
        event,
        ChaosWebhookConfig(mode=WebhookChaosMode.INVALID_SIGNATURE, tamper_secret="wrong_secret"),
    )
    assert chaos_res[0].status_code == 401
    assert "Invalid signature" in chaos_res[0].response_body


def test_chaos_clock_skew(mock_receiver):
    client, received = mock_receiver
    emitter = WebhookEmitter(
        target_url="http://testserver/webhook",
        secret="whsec_skew_secret",
        scheme=WebhookSignatureScheme.STRIPE_V1,
        client=client,
    )
    dispatcher = ChaosWebhookDispatcher(emitter)

    event = WebhookEvent(
        event_id="evt_skew_test",
        event_type="customer.subscription.created",
        payload={"sub_id": "sub_999"},
    )

    config = ChaosWebhookConfig(
        mode=WebhookChaosMode.CLOCK_SKEW,
        clock_skew_seconds=1200,
        skew_direction="past",
    )

    now = int(time.time())
    results = dispatcher.dispatch_with_chaos(event, config)

    assert len(results) == 1
    # Check that timestamp_used was skewed backwards ~1200 seconds
    assert results[0].timestamp_used <= now - 1100
