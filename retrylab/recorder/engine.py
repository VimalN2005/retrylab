"""
RetryLab Sanitized Traffic Recording & Offline Fixture Replay Engine.
Records live API interactions with automated PII/secret scrubbing and replays them offline.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, List
import httpx
from pydantic import BaseModel, Field

from retrylab.models import FaultScenario, FaultType
from retrylab.security.redactor import DataRedactor


class RecordedInteraction(BaseModel):
    """A sanitized outbound request and corresponding response pair."""

    url: str
    method: str
    request_headers: dict[str, str] = Field(default_factory=dict)
    request_body: str = ""
    status_code: int = 200
    response_headers: dict[str, str] = Field(default_factory=dict)
    response_body: str = ""
    timestamp: float = Field(default_factory=time.time)


class TrafficRecorder:
    """
    Captures live HTTP requests and responses, redacting sensitive tokens before persistence.
    """

    def __init__(self, redactor: DataRedactor | None = None) -> None:
        self.redactor = redactor or DataRedactor()
        self.interactions: list[RecordedInteraction] = []

    def record(
        self,
        request: httpx.Request,
        response: httpx.Response,
    ) -> RecordedInteraction:
        """Sanitizes and stores a request/response transaction."""
        req_headers = self.redactor.redact_headers(dict(request.headers))
        try:
            req_body = self.redactor.redact_body(request.read())
        except Exception:
            req_body = ""

        resp_headers = self.redactor.redact_headers(dict(response.headers))
        try:
            resp_body = self.redactor.redact_body(response.read())
        except Exception:
            resp_body = ""

        interaction = RecordedInteraction(
            url=str(request.url),
            method=request.method,
            request_headers=req_headers,
            request_body=req_body,
            status_code=response.status_code,
            response_headers=resp_headers,
            response_body=resp_body,
        )
        self.interactions.append(interaction)
        return interaction

    def save(self, file_path: Path | str) -> None:
        """Saves recorded interactions as a formatted JSON fixture."""
        path = Path(file_path)
        data = [i.model_dump() for i in self.interactions]
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, file_path: Path | str) -> list[RecordedInteraction]:
        """Loads recorded interactions from a JSON fixture file."""
        path = Path(file_path)
        raw_list = json.loads(path.read_text(encoding="utf-8"))
        return [RecordedInteraction(**item) for item in raw_list]


class ReplayTransport(httpx.BaseTransport):
    """
    Offline HTTPX transport that replays responses from recorded fixtures,
    with optional fault injection on matching requests.
    """

    def __init__(
        self,
        interactions: list[RecordedInteraction],
        scenario: FaultScenario | None = None,
    ) -> None:
        self.interactions = interactions
        self.scenario = scenario
        self.attempts: int = 0

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        method_str = request.method
        self.attempts += 1

        # Check if fault scenario applies
        if self.scenario and self.scenario.should_inject_fault(url_str, method_str):
            self.scenario.record_attempt(
                url=url_str,
                method=method_str,
                headers=dict(request.headers),
                body=request.read(),
                injected=True,
            )
            if self.scenario.fault == FaultType.TIMEOUT:
                raise httpx.ReadTimeout(f"Simulated ReadTimeout for {url_str} during replay", request=request)
            return httpx.Response(
                status_code=self.scenario.status_code or 500,
                headers=self.scenario.custom_headers,
                content=(self.scenario.custom_body or '{"error": "replay_fault"}').encode(),
                request=request,
            )

        # Match interaction from recorded fixture
        matched = None
        for item in self.interactions:
            if item.url == url_str and item.method.upper() == method_str.upper():
                matched = item
                break

        if matched is not None:
            return httpx.Response(
                status_code=matched.status_code,
                headers=matched.response_headers,
                content=matched.response_body.encode("utf-8"),
                request=request,
            )

        # Fallback 404 if not found in recording
        return httpx.Response(
            status_code=404,
            content=json.dumps({"error": f"No recorded fixture for {method_str} {url_str}"}).encode(),
            request=request,
        )
