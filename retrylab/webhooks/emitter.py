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
