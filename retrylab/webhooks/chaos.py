"""
RetryLab Chaos Webhook Dispatcher.
Injects real-world delivery failures into webhook ingestion pipelines:
- At-least-once delivery duplicates
- Out-of-order event ordering
- Cryptographic signature tampering (replay/forgery simulation)
- Timestamp drift and clock skew (tolerance checks)
"""

from __future__ import annotations

import copy
import time
from enum import Enum
from typing import Any
import httpx
from pydantic import BaseModel, Field

from retrylab.webhooks.emitter import WebhookEmitter, WebhookEvent, WebhookSignatureScheme


class WebhookChaosMode(str, Enum):
    """Chaos injection modes for webhook transmissions."""

    NONE = "none"
    DUPLICATE = "duplicate"
    OUT_OF_ORDER = "out_of_order"
    INVALID_SIGNATURE = "invalid_signature"
    CLOCK_SKEW = "clock_skew"


class ChaosWebhookConfig(BaseModel):
    """Configuration options for webhook chaos generation."""

    mode: WebhookChaosMode = WebhookChaosMode.NONE
    duplicate_count: int = 2
    clock_skew_seconds: int = 600  # 10 minutes past/future skew
    skew_direction: str = "past"   # "past" or "future"
    tamper_secret: str = "tampered_invalid_secret_key"


class DispatchedWebhookResult(BaseModel):
    """Result of a chaos-injected webhook delivery attempt."""

    event_id: str
    event_type: str
    status_code: int
    chaos_mode: WebhookChaosMode
    attempt_index: int
    timestamp_used: int
    headers_sent: dict[str, str] = Field(default_factory=dict)
    response_body: str = ""
    success: bool


class ChaosWebhookDispatcher:
    """
    Wraps WebhookEmitter to inject realistic webhook delivery chaos.
    Used to test receiver idempotency, ordering buffers, and signature verification.
    """

    def __init__(self, emitter: WebhookEmitter) -> None:
        self.emitter = emitter

    def dispatch_with_chaos(
        self,
        event: WebhookEvent,
        config: ChaosWebhookConfig,
    ) -> list[DispatchedWebhookResult]:
        """
        Dispatches a single event under the specified chaos configuration.
        Returns a list of dispatch results (multiple if duplicate mode).
        """
        results: list[DispatchedWebhookResult] = []
        base_time = int(time.time())

        if config.mode == WebhookChaosMode.DUPLICATE:
            # Emit the same event payload and event_id multiple times
            for idx in range(config.duplicate_count):
                resp = self.emitter.dispatch(event=event, timestamp=base_time)
                results.append(
                    DispatchedWebhookResult(
                        event_id=event.event_id,
                        event_type=event.event_type,
                        status_code=resp.status_code,
                        chaos_mode=config.mode,
                        attempt_index=idx + 1,
                        timestamp_used=base_time,
                        headers_sent=dict(resp.request.headers),
                        response_body=resp.text,
                        success=resp.is_success,
                    )
                )

        elif config.mode == WebhookChaosMode.INVALID_SIGNATURE:
            # Tamper the secret so HMAC signature check on receiver fails
            corrupt_emitter = WebhookEmitter(
                target_url=self.emitter.target_url,
                secret=config.tamper_secret,
                scheme=self.emitter.scheme,
                client=self.emitter._client,
            )
            resp = corrupt_emitter.dispatch(event=event, timestamp=base_time)
            results.append(
                DispatchedWebhookResult(
                    event_id=event.event_id,
                    event_type=event.event_type,
                    status_code=resp.status_code,
                    chaos_mode=config.mode,
                    attempt_index=1,
                    timestamp_used=base_time,
                    headers_sent=dict(resp.request.headers),
                    response_body=resp.text,
                    success=resp.is_success,
                )
            )

        elif config.mode == WebhookChaosMode.CLOCK_SKEW:
            # Apply clock drift in past or future
            skew = config.clock_skew_seconds if config.skew_direction == "future" else -config.clock_skew_seconds
            skewed_timestamp = base_time + skew
            resp = self.emitter.dispatch(event=event, timestamp=skewed_timestamp)
            results.append(
                DispatchedWebhookResult(
                    event_id=event.event_id,
                    event_type=event.event_type,
                    status_code=resp.status_code,
                    chaos_mode=config.mode,
                    attempt_index=1,
                    timestamp_used=skewed_timestamp,
                    headers_sent=dict(resp.request.headers),
                    response_body=resp.text,
                    success=resp.is_success,
                )
            )

        else:
            # Standard single transmission
            resp = self.emitter.dispatch(event=event, timestamp=base_time)
            results.append(
                DispatchedWebhookResult(
                    event_id=event.event_id,
                    event_type=event.event_type,
                    status_code=resp.status_code,
                    chaos_mode=config.mode,
                    attempt_index=1,
                    timestamp_used=base_time,
                    headers_sent=dict(resp.request.headers),
                    response_body=resp.text,
                    success=resp.is_success,
                )
            )

        return results

    def dispatch_batch(
        self,
        events: list[WebhookEvent],
        config: ChaosWebhookConfig,
    ) -> list[DispatchedWebhookResult]:
        """
        Dispatches an entire batch of webhook events.
        If config.mode == OUT_OF_ORDER, reverses the transmission order.
        """
        results: list[DispatchedWebhookResult] = []

        target_events = list(events)
        if config.mode == WebhookChaosMode.OUT_OF_ORDER:
            # Invert order of arrival to simulate network packet reordering
            target_events = list(reversed(target_events))

        for event in target_events:
            res_list = self.dispatch_with_chaos(event, config)
            results.extend(res_list)

        return results
