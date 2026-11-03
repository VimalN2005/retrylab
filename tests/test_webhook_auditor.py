"""
Tests for WebhookReceiverAuditor resilience & security auditing suite.
"""

import hashlib
import hmac
import time
import httpx
import pytest

from retrylab.webhooks import (
    WebhookAuditReport,
    WebhookReceiverAuditor,
    WebhookSignatureScheme,
)


def create_resilient_receiver_client(secret: str) -> httpx.Client:
    """Mock receiver that enforces Stripe-style signature verification, clock skew check, and idempotency."""
    seen_event_ids = set()

    def handler(request: httpx.Request) -> httpx.Response:
        sig_header = request.headers.get("Stripe-Signature", "")
        if not sig_header:
            return httpx.Response(status_code=401, json={"error": "Missing signature"})

        parts = dict(kv.split("=", 1) for kv in sig_header.split(","))
        ts_str = parts.get("t", "0")
        v1 = parts.get("v1", "")

        try:
            ts = int(ts_str)
        except ValueError:
            return httpx.Response(status_code=400, json={"error": "Malformed timestamp"})

        # Clock skew tolerance check: 300 seconds (5 min)
        now = int(time.time())
        if abs(now - ts) > 300:
            return httpx.Response(status_code=400, json={"error": "Timestamp outside tolerance window"})

        # Signature check
        expected = hmac.new(
            secret.encode(),
            f"{ts}.".encode() + request.content,
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(v1, expected):
            return httpx.Response(status_code=401, json={"error": "Invalid HMAC signature"})

        # Idempotency check: duplicate event handling
        evt_id = request.headers.get("X-Event-Id", "")
        if evt_id in seen_event_ids:
            return httpx.Response(status_code=200, json={"status": "duplicate_ignored"})
        seen_event_ids.add(evt_id)

        return httpx.Response(status_code=200, json={"status": "processed"})

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_auditor_on_compliant_receiver():
    secret = "whsec_secure_production_key"
    client = create_resilient_receiver_client(secret)

    auditor = WebhookReceiverAuditor(
        target_url="http://mock-app/webhooks/stripe",
        secret=secret,
        scheme=WebhookSignatureScheme.STRIPE_V1,
        client=client,
    )

    report: WebhookAuditReport = auditor.run_audit(check_clock_skew=True)

    assert report.all_passed is True
    assert report.total_checks == 4
    assert report.passed_checks == 4
    assert report.failed_checks == 0


def test_auditor_detects_signature_vulnerability():
    # Flawed receiver: doesn't verify signatures, accepts everything with 200
    def naive_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=200, json={"ok": True})

    client = httpx.Client(transport=httpx.MockTransport(naive_handler))

    auditor = WebhookReceiverAuditor(
        target_url="http://insecure-app/webhooks",
        secret="secret123",
        scheme=WebhookSignatureScheme.STRIPE_V1,
        client=client,
    )

    report = auditor.run_audit(check_clock_skew=True)

    assert report.all_passed is False
    # Check that forged signature rejection failed
    forged_check = next(c for c in report.checks if c.check_name == "forged_signature_rejection")
    assert forged_check.passed is False
    assert forged_check.status_code == 200


def test_auditor_detects_duplicate_crash():
    # Flawed receiver: crashes with 500 when duplicate event is received
    seen = set()

    def crashing_handler(request: httpx.Request) -> httpx.Response:
        evt_id = request.headers.get("X-Event-Id", "")
        sig = request.headers.get("Stripe-Signature", "")
        if "wrong_unauthorized_key" in sig or "tampered" in sig:
            return httpx.Response(status_code=401)
        if evt_id in seen:
            return httpx.Response(status_code=500, json={"error": "Unique constraint violation: duplicate event ID"})
        seen.add(evt_id)
        return httpx.Response(status_code=200, json={"ok": True})

    client = httpx.Client(transport=httpx.MockTransport(crashing_handler))

    auditor = WebhookReceiverAuditor(
        target_url="http://crashing-app/webhooks",
        secret="secret123",
        scheme=WebhookSignatureScheme.STRIPE_V1,
        client=client,
    )

    report = auditor.run_audit(check_clock_skew=False)
    dup_check = next(c for c in report.checks if c.check_name == "idempotent_duplicate_handling")
    assert dup_check.passed is False
    assert dup_check.status_code == 500
