"""
RetryLab In-Process Webhook Mock Receiver & Fault Simulator.
Captures, verifies, and audits incoming webhook events with configurable failure policies
(e.g., fail first N deliveries, inject processing latency, reject unauthorized signatures).
"""

from __future__ import annotations

import json
import time
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Callable
import httpx
from pydantic import BaseModel, Field

from retrylab.webhooks.emitter import (
    WebhookSignatureScheme,
    verify_webhook_signature,
)


class ReceivedWebhookEvent(BaseModel):
    """Record of an inbound webhook event captured by the mock receiver."""

    id: str = Field(default_factory=lambda: f"rec_evt_{uuid.uuid4().hex[:10]}")
    event_id: str | None = None
    event_type: str | None = None
    timestamp: float = Field(default_factory=time.time)
    headers: dict[str, str] = Field(default_factory=dict)
    body_raw: bytes = b""
    payload: dict[str, Any] | None = None
    signature_valid: bool | None = None
    signature_reason: str = ""
    injected_fault: str | None = None
    response_status: int = 200


class WebhookReceiverFaultConfig(BaseModel):
    """Rules for simulating webhook ingestion faults."""

    fail_first_n: int = 0
    fail_status_code: int = 500
    fail_response_body: dict[str, Any] = Field(
        default_factory=lambda: {"error": "Simulated temporary webhook receiver failure"}
    )
    delay_seconds: float = 0.0
    reject_invalid_signatures: bool = True


class MockWebhookReceiver:
    """
    Mock webhook receiver for testing inbound webhook deliveries, redelivery schedules,
    and payload integrity.
    """

    def __init__(
        self,
        secret: str | None = None,
        scheme: WebhookSignatureScheme = WebhookSignatureScheme.STRIPE_V1,
        fault_config: WebhookReceiverFaultConfig | None = None,
        on_event_received: Callable[[ReceivedWebhookEvent], None] | None = None,
    ) -> None:
        self.secret = secret
        self.scheme = scheme
        self.fault_config = fault_config or WebhookReceiverFaultConfig()
        self.on_event_received = on_event_received

        self._events: list[ReceivedWebhookEvent] = []
        self._request_counter = 0

    @property
    def request_count(self) -> int:
        return self._request_counter

    @property
    def events(self) -> list[ReceivedWebhookEvent]:
        return list(self._events)

    def clear(self) -> None:
        """Clears all captured events and resets the request counter."""
        self._events.clear()
        self._request_counter = 0

    def handle_request(
        self,
        method: str,
        path: str,
        headers: dict[str, str],
        body: bytes,
    ) -> tuple[int, dict[str, str], bytes]:
        """
        Processes an incoming HTTP request, records it, evaluates fault rules, and returns
        (status_code, response_headers, response_bytes).
        """
        self._request_counter += 1
        now = time.time()

        # Extract normalized headers
        norm_headers = {k.lower(): v for k, v in headers.items()}
        event_id = (
            norm_headers.get("x-event-id")
            or norm_headers.get("x-github-delivery")
            or norm_headers.get("webhook-id")
        )
        event_type = (
            norm_headers.get("x-event-type")
            or norm_headers.get("x-github-event")
            or norm_headers.get("webhook-type")
        )

        # Parse JSON body if applicable
        parsed_payload: dict[str, Any] | None = None
        try:
            if body:
                parsed_payload = json.loads(body.decode("utf-8"))
                if not event_type and isinstance(parsed_payload, dict):
                    event_type = parsed_payload.get("type") or parsed_payload.get("event")
                if not event_id and isinstance(parsed_payload, dict):
                    event_id = parsed_payload.get("id") or parsed_payload.get("event_id")
        except Exception:
            pass

        # Optional delay injection
        if self.fault_config.delay_seconds > 0:
            time.sleep(self.fault_config.delay_seconds)

        # Signature verification if secret is configured
        sig_valid: bool | None = None
        sig_reason = "No secret configured"
        if self.secret is not None:
            sig_valid, sig_reason = verify_webhook_signature(
                headers=headers,
                body=body,
                secret=self.secret,
                scheme=self.scheme,
            )

        # Check if signature rejection is triggered
        if self.secret is not None and not sig_valid and self.fault_config.reject_invalid_signatures:
            resp_body = json.dumps({"error": f"Invalid signature: {sig_reason}"}).encode("utf-8")
            event_record = ReceivedWebhookEvent(
                event_id=event_id,
                event_type=event_type,
                timestamp=now,
                headers=headers,
                body_raw=body,
                payload=parsed_payload,
                signature_valid=sig_valid,
                signature_reason=sig_reason,
                injected_fault="invalid_signature_rejection",
                response_status=401,
            )
            self._events.append(event_record)
            if self.on_event_received:
                self.on_event_received(event_record)
            return 401, {"Content-Type": "application/json"}, resp_body

        # Check if fail_first_n fault is active
        if self._request_counter <= self.fault_config.fail_first_n:
            fault_status = self.fault_config.fail_status_code
            resp_body = json.dumps(self.fault_config.fail_response_body).encode("utf-8")
            event_record = ReceivedWebhookEvent(
                event_id=event_id,
                event_type=event_type,
                timestamp=now,
                headers=headers,
                body_raw=body,
                payload=parsed_payload,
                signature_valid=sig_valid,
                signature_reason=sig_reason,
                injected_fault=f"fail_first_n ({self._request_counter}/{self.fault_config.fail_first_n})",
                response_status=fault_status,
            )
            self._events.append(event_record)
            if self.on_event_received:
                self.on_event_received(event_record)
            return fault_status, {"Content-Type": "application/json"}, resp_body

        # Successful acknowledgment
        success_body = json.dumps({"received": True, "event_id": event_id}).encode("utf-8")
        event_record = ReceivedWebhookEvent(
            event_id=event_id,
            event_type=event_type,
            timestamp=now,
            headers=headers,
            body_raw=body,
            payload=parsed_payload,
            signature_valid=sig_valid,
            signature_reason=sig_reason,
            injected_fault=None,
            response_status=200,
        )
        self._events.append(event_record)
        if self.on_event_received:
            self.on_event_received(event_record)

        return 200, {"Content-Type": "application/json"}, success_body

    def as_transport(self) -> httpx.MockTransport:
        """Creates an HTTPX MockTransport that routes requests directly to this receiver."""

        def handler(request: httpx.Request) -> httpx.Response:
            status, headers, content = self.handle_request(
                method=request.method,
                path=str(request.url.path),
                headers=dict(request.headers),
                body=request.content,
            )
            return httpx.Response(status_code=status, headers=headers, content=content)

        return httpx.MockTransport(handler)

    def get_events_by_type(self, event_type: str) -> list[ReceivedWebhookEvent]:
        """Returns all received events matching the specified type."""
        return [e for e in self._events if e.event_type == event_type]

    def get_event_by_id(self, event_id: str) -> ReceivedWebhookEvent | None:
        """Returns the first received event matching the specified ID."""
        for e in self._events:
            if e.event_id == event_id:
                return e
        return None

    def assert_event_received(self, event_type: str, count: int | None = None) -> None:
        """Asserts that at least one (or an exact count of) event with the given type was received."""
        matching = self.get_events_by_type(event_type)
        if count is not None:
            assert len(matching) == count, (
                f"Expected {count} events of type '{event_type}', but received {len(matching)}."
            )
        else:
            assert len(matching) > 0, f"Expected event of type '{event_type}', but none was received."

    def assert_all_signatures_valid(self) -> None:
        """Asserts that all captured events possess valid cryptographic signatures."""
        for e in self._events:
            assert e.signature_valid is True, (
                f"Event {e.id} ({e.event_type}) has invalid signature: {e.signature_reason}"
            )


def create_receiver_server(
    receiver: MockWebhookReceiver,
    host: str = "127.0.0.1",
    port: int = 8085,
) -> HTTPServer:
    """
    Creates an HTTPServer running MockWebhookReceiver for external HTTP testing or CLI listening.
    """

    class WebhookHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length) if length > 0 else b""
            status, resp_headers, resp_content = receiver.handle_request(
                method="POST",
                path=self.path,
                headers=dict(self.headers),
                body=body,
            )
            self.send_response(status)
            for k, v in resp_headers.items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(resp_content)

        def do_GET(self) -> None:
            if self.path == "/_retrylab/events":
                events_json = json.dumps([e.model_dump(mode="json") for e in receiver.events]).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(events_json)
            else:
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"RetryLab Mock Webhook Receiver is active.")

        def log_message(self, format: str, *args: Any) -> None:
            # Suppress default stdout log spam
            pass

    return HTTPServer((host, port), WebhookHandler)
