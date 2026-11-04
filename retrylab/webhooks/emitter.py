"""
RetryLab Synthetic Webhook Emitter & Cryptographic Signature Engine.
Dispatches HMAC-signed webhook events to test receiver security and ingestion pipelines.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from enum import Enum
from typing import Any
import httpx
from pydantic import BaseModel, Field


class WebhookSignatureScheme(str, Enum):
    """Supported cryptographic webhook signing standards."""

    STRIPE_V1 = "stripe_v1"        # Header: Stripe-Signature: t={timestamp},v1={hash}
    GITHUB_SHA256 = "github_sha256"  # Header: X-Hub-Signature-256: sha256={hash}
    HMAC_SHA256 = "hmac_sha256"      # Header: X-Signature: {hash}


class WebhookEvent(BaseModel):
    """Definition of an inbound webhook event."""

    event_id: str
    event_type: str
    payload: dict[str, Any]
    headers: dict[str, str] = Field(default_factory=dict)


def compute_webhook_signature(
    body: bytes,
    secret: str,
    scheme: WebhookSignatureScheme,
    timestamp: int | None = None,
) -> tuple[dict[str, str], int]:
    """
    Computes authentic webhook security headers according to provider specifications.
    Returns (headers_dict, timestamp_used).
    """
    ts = timestamp if timestamp is not None else int(time.time())
    secret_bytes = secret.encode("utf-8")

    if scheme == WebhookSignatureScheme.STRIPE_V1:
        # Stripe signed payload is: "{timestamp}.{body}"
        signed_payload = f"{ts}.".encode("utf-8") + body
        sig = hmac.new(secret_bytes, signed_payload, hashlib.sha256).hexdigest()
        header_val = f"t={ts},v1={sig}"
        return {"Stripe-Signature": header_val}, ts

    elif scheme == WebhookSignatureScheme.GITHUB_SHA256:
        sig = hmac.new(secret_bytes, body, hashlib.sha256).hexdigest()
        return {"X-Hub-Signature-256": f"sha256={sig}"}, ts

    elif scheme == WebhookSignatureScheme.HMAC_SHA256:
        sig = hmac.new(secret_bytes, body, hashlib.sha256).hexdigest()
        return {"X-Signature": sig, "X-Timestamp": str(ts)}, ts

    raise ValueError(f"Unsupported signature scheme: {scheme}")


def verify_webhook_signature(
    headers: dict[str, str],
    body: bytes,
    secret: str,
    scheme: WebhookSignatureScheme,
    tolerance_seconds: int | None = 300,
) -> tuple[bool, str]:
    """
    Cryptographically verifies an incoming webhook request signature.
    Returns (is_valid, reason_message).
    """
    # Normalize header keys to lowercase for robust lookup
    norm_headers = {k.lower(): v for k, v in headers.items()}
    secret_bytes = secret.encode("utf-8")

    if scheme == WebhookSignatureScheme.STRIPE_V1:
        sig_header = norm_headers.get("stripe-signature")
        if not sig_header:
            return False, "Missing 'Stripe-Signature' header"

        parts: dict[str, str] = {}
        for item in sig_header.split(","):
            if "=" in item:
                k, v = item.strip().split("=", 1)
                parts[k] = v

        ts_str = parts.get("t")
        v1_sig = parts.get("v1")
        if not ts_str or not v1_sig:
            return False, "Malformed 'Stripe-Signature' header; missing 't' or 'v1'"

        try:
            ts = int(ts_str)
        except ValueError:
            return False, f"Invalid timestamp value in Stripe-Signature: {ts_str}"

        if tolerance_seconds is not None:
            if abs(time.time() - ts) > tolerance_seconds:
                return False, f"Timestamp {ts} outside tolerance window of {tolerance_seconds}s"

        signed_payload = f"{ts}.".encode("utf-8") + body
        expected_sig = hmac.new(secret_bytes, signed_payload, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(v1_sig, expected_sig):
            return False, "Signature mismatch"
        return True, "Valid Stripe signature"

    elif scheme == WebhookSignatureScheme.GITHUB_SHA256:
        sig_header = norm_headers.get("x-hub-signature-256")
        if not sig_header:
            return False, "Missing 'X-Hub-Signature-256' header"

        if not sig_header.startswith("sha256="):
            return False, "Malformed 'X-Hub-Signature-256'; must start with 'sha256='"

        provided_sig = sig_header[len("sha256=") :]
        expected_sig = hmac.new(secret_bytes, body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(provided_sig, expected_sig):
            return False, "Signature mismatch"
        return True, "Valid GitHub SHA256 signature"

    elif scheme == WebhookSignatureScheme.HMAC_SHA256:
        sig_header = norm_headers.get("x-signature")
        if not sig_header:
            return False, "Missing 'X-Signature' header"

        expected_sig = hmac.new(secret_bytes, body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig_header, expected_sig):
            return False, "Signature mismatch"
        return True, "Valid HMAC signature"

    return False, f"Unsupported signature scheme: {scheme}"


class WebhookEmitter:
    """
    Dispatches cryptographic webhook events to local or remote endpoints.
    """

    def __init__(
        self,
        target_url: str,
        secret: str,
        scheme: WebhookSignatureScheme = WebhookSignatureScheme.STRIPE_V1,
        client: httpx.Client | None = None,
    ) -> None:
        self.target_url = target_url
        self.secret = secret
        self.scheme = scheme
        self._client = client

    def dispatch(
        self,
        event: WebhookEvent,
        timestamp: int | None = None,
        custom_headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """Signs and transmits the webhook event to the configured target URL."""
        body_bytes = json.dumps(event.payload, separators=(",", ":")).encode("utf-8")
        sig_headers, _ = compute_webhook_signature(
            body=body_bytes,
            secret=self.secret,
            scheme=self.scheme,
            timestamp=timestamp,
        )

        all_headers = {
            "Content-Type": "application/json",
            "User-Agent": "RetryLab-Webhook-Emitter/1.0",
            "X-Event-Id": event.event_id,
            "X-Event-Type": event.event_type,
            **sig_headers,
            **event.headers,
            **(custom_headers or {}),
        }

        if self._client is not None:
            return self._client.post(self.target_url, content=body_bytes, headers=all_headers)

        with httpx.Client() as client:
            return client.post(self.target_url, content=body_bytes, headers=all_headers)
