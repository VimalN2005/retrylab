"""
RetryLab Webhook Forwarder & Fixture Replay Engine.
Forwards captured or recorded webhook traffic to local/remote applications with optional
jitter, header mutation, and duplicate injection.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable
import httpx
from pydantic import BaseModel, Field

from retrylab.webhooks.server import ReceivedWebhookEvent


class ForwardingRule(BaseModel):
    """Rules applied when forwarding webhook events."""

    target_url: str
    preserve_headers: bool = True
    inject_delay_seconds: float = 0.0
    duplicate_count: int = 1
    strip_signature: bool = False
    custom_headers: dict[str, str] = Field(default_factory=dict)


class ForwardingResult(BaseModel):
    """Result of an individual webhook forwarding attempt."""

    event_id: str | None
    event_type: str | None
    target_url: str
    status_code: int
    latency_ms: float
    attempt: int
    success: bool
    error_message: str | None = None
    response_body: str = ""


class WebhookForwarder:
    """
    Forwards captured webhook events to local application endpoints.
    Used for local webhook tunnels, proxying, and CI integration testing.
    """

    def __init__(
        self,
        rule: ForwardingRule,
        client: httpx.Client | None = None,
    ) -> None:
        self.rule = rule
        self._client = client
        self._history: list[ForwardingResult] = []

    @property
    def history(self) -> list[ForwardingResult]:
        return list(self._history)

    def forward_event(self, event: ReceivedWebhookEvent) -> list[ForwardingResult]:
        """Forwards a single received event according to configured rules."""
        results: list[ForwardingResult] = []

        headers = dict(event.headers) if self.rule.preserve_headers else {}
        headers["Content-Type"] = "application/json"
        headers["User-Agent"] = "RetryLab-Webhook-Forwarder/1.0"

        if self.rule.strip_signature:
            for k in list(headers.keys()):
                if "signature" in k.lower() or "hub" in k.lower():
                    headers.pop(k, None)

        headers.update(self.rule.custom_headers)
        body = event.body_raw

        for attempt in range(1, self.rule.duplicate_count + 1):
            if self.rule.inject_delay_seconds > 0:
                time.sleep(self.rule.inject_delay_seconds)

            t0 = time.perf_counter()
            try:
                if self._client is not None:
                    resp = self._client.post(self.rule.target_url, content=body, headers=headers)
                else:
                    with httpx.Client(timeout=10.0) as cli:
                        resp = cli.post(self.rule.target_url, content=body, headers=headers)

                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                res = ForwardingResult(
                    event_id=event.event_id,
                    event_type=event.event_type,
                    target_url=self.rule.target_url,
                    status_code=resp.status_code,
                    latency_ms=round(elapsed_ms, 2),
                    attempt=attempt,
                    success=resp.is_success,
                    response_body=resp.text[:200],
                )
            except Exception as exc:
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                res = ForwardingResult(
                    event_id=event.event_id,
                    event_type=event.event_type,
                    target_url=self.rule.target_url,
                    status_code=0,
                    latency_ms=round(elapsed_ms, 2),
                    attempt=attempt,
                    success=False,
                    error_message=str(exc),
                )

            results.append(res)
            self._history.append(res)

        return results


class WebhookReplayEngine:
    """
    Replays recorded webhook event fixtures against target endpoints for offline verification.
    """

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client

    def load_fixture_file(self, file_path: Path | str) -> list[ReceivedWebhookEvent]:
        """Loads a list of recorded events from a JSON file."""
        p = Path(file_path)
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [ReceivedWebhookEvent.model_validate(item) for item in data]
        raise ValueError(f"Fixture file '{file_path}' must contain a JSON array of events.")

    def replay_events(
        self,
        events: list[ReceivedWebhookEvent],
        target_url: str,
        delay_between_events: float = 0.0,
        reverse_order: bool = False,
    ) -> list[ForwardingResult]:
        """
        Replays recorded events against the specified target URL.
        """
        rule = ForwardingRule(target_url=target_url)
        forwarder = WebhookForwarder(rule=rule, client=self._client)

        target_events = list(reversed(events)) if reverse_order else list(events)
        all_results: list[ForwardingResult] = []

        for idx, evt in enumerate(target_events):
            if idx > 0 and delay_between_events > 0:
                time.sleep(delay_between_events)
            results = forwarder.forward_event(evt)
            all_results.extend(results)

        return all_results
