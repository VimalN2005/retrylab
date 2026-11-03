"""
Tests for WebhookEmitter and cryptographic signature verification.
"""

import hashlib
import hmac
import json
import httpx
import pytest

from retrylab.webhooks import (
    WebhookEmitter,
    WebhookEvent,
    WebhookSignatureScheme,
    compute_webhook_signature,
)


def test_stripe_signature_calculation():
    body = b'{"type":"charge.succeeded","amount":1000}'
    secret = "whsec_test_secret_key_123"
    timestamp = 1730000000

    headers, ts = compute_webhook_signature(
        body=body,
        secret=secret,
        scheme=WebhookSignatureScheme.STRIPE_V1,
        timestamp=timestamp,
    )

    assert "Stripe-Signature" in headers
    sig_val = headers["Stripe-Signature"]
    assert sig_val.startswith(f"t={timestamp},v1=")

    # Manually verify HMAC
    expected_mac = hmac.new(
        secret.encode(),
        f"{timestamp}.".encode() + body,
        hashlib.sha256,
    ).hexdigest()
    assert f"v1={expected_mac}" in sig_val


def test_github_signature_calculation():
    body = b'{"action":"opened","pull_request":{"id":42}}'
    secret = "gh_secret_xyz"

    headers, _ = compute_webhook_signature(
        body=body,
        secret=secret,
        scheme=WebhookSignatureScheme.GITHUB_SHA256,
    )

    assert "X-Hub-Signature-256" in headers
    expected_mac = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert headers["X-Hub-Signature-256"] == f"sha256={expected_mac}"


def test_webhook_emitter_dispatch():
    captured_requests = []

    def mock_handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        return httpx.Response(status_code=200, json={"received": True})

    mock_client = httpx.Client(transport=httpx.MockTransport(mock_handler))

    emitter = WebhookEmitter(
        target_url="http://localhost:8000/api/v1/webhook",
        secret="whsec_12345",
        scheme=WebhookSignatureScheme.STRIPE_V1,
        client=mock_client,
    )

    event = WebhookEvent(
        event_id="evt_test_9988",
        event_type="payment_intent.succeeded",
        payload={"amount": 2500, "currency": "usd"},
    )

    resp = emitter.dispatch(event)
    assert resp.status_code == 200
    assert resp.json()["received"] is True

    # Assert captured HTTP request
    assert len(captured_requests) == 1
    req = captured_requests[0]
    assert req.headers["X-Event-Id"] == "evt_test_9988"
    assert req.headers["X-Event-Type"] == "payment_intent.succeeded"
    assert "Stripe-Signature" in req.headers
