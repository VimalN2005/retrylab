"""
RetryLab Core Data Models & Scenario Definitions.
"""

from __future__ import annotations

import fnmatch
import time
from enum import Enum
from typing import Any
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr


class FaultType(str, Enum):
    """Supported fault injection types."""

    TIMEOUT = "timeout"
    RATE_LIMIT_429 = "rate_limit_429"
    SERVER_ERROR_500 = "server_error_500"
    BAD_GATEWAY_502 = "bad_gateway_502"
    SERVICE_UNAVAILABLE_503 = "service_unavailable_503"
    GATEWAY_TIMEOUT_504 = "gateway_timeout_504"
    CONNECTION_RESET = "connection_reset"
    LATENCY = "latency"


class RecordedRequest(BaseModel):
    """Metadata recorded for an intercepted request."""

    url: str
    method: str
    headers: dict[str, str]
    body: bytes
    timestamp: float = Field(default_factory=time.time)
    was_fault_injected: bool = False
    injected_fault: FaultType | None = None


class FaultScenario(BaseModel):
    """
    Defines a deterministic fault injection scenario for an outbound target.

    Attributes:
        target: URL or wildcard pattern to intercept (e.g. 'https://api.stripe.com/v1/*')
        fault: Type of fault to inject (e.g. FaultType.TIMEOUT, FaultType.RATE_LIMIT_429)
        fail_count: Number of consecutive matching requests that will experience the fault.
                    Subsequent requests will pass through or recover.
        method: Optional HTTP method constraint (e.g. 'POST', 'GET'). If None, matches all methods.
        delay_seconds: Artificial delay to introduce before responding or raising timeout.
        status_code: Custom HTTP status code to return (overrides default for fault type).
        custom_headers: Custom HTTP headers to include in the simulated response.
        custom_body: Custom string or JSON payload to return in simulated response.
        retry_after_seconds: Value for 'Retry-After' header in 429 / 503 responses.
        expect_idempotency_header: Optional header name (e.g. 'Idempotency-Key') to enforce on retries.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str = "default_scenario"
    target: str
    fault: FaultType
    fail_count: int = Field(default=1, ge=1)
    method: str | None = None
    delay_seconds: float = Field(default=0.0, ge=0.0)
    status_code: int | None = None
    custom_headers: dict[str, str] = Field(default_factory=dict)
    custom_body: str | None = None
    retry_after_seconds: int = Field(default=2, ge=0)
    expect_idempotency_header: str | None = None

    # Internal state tracking
    _attempts: int = PrivateAttr(default=0)
    _recorded_requests: list[RecordedRequest] = PrivateAttr(default_factory=list)

    def matches(self, url: str, method: str) -> bool:
        """Check if an outgoing request matches this scenario's rules."""
        # Method match check
        if self.method and self.method.upper() != method.upper():
            return False

        # Wildcard / fnmatch URL matching
        # Allow exact match or pattern match
        if fnmatch.fnmatch(url, self.target):
            return True

        # Also match prefix if target ends with /* or similar
        clean_target = self.target.rstrip("*")
        if url.startswith(clean_target):
            return True

        return False

    def should_inject_fault(self, url: str, method: str) -> bool:
        """Determines if the next matching request should have a fault injected."""
        if not self.matches(url, method):
            return False
        return self._attempts < self.fail_count

    def record_attempt(
        self,
        url: str,
        method: str,
        headers: dict[str, str],
        body: bytes,
        injected: bool,
    ) -> RecordedRequest:
        """Record an attempt and increment internal counter."""
        self._attempts += 1
        record = RecordedRequest(
            url=url,
            method=method,
            headers=headers,
            body=body,
            was_fault_injected=injected,
            injected_fault=self.fault if injected else None,
        )
        self._recorded_requests.append(record)
        return record

    @property
    def total_attempts(self) -> int:
        """Return total matching requests seen so far."""
        return self._attempts

    @property
    def recorded_requests(self) -> list[RecordedRequest]:
        """Return history of intercepted requests."""
        return list(self._recorded_requests)

    def reset(self) -> None:
        """Reset scenario state for a clean test run."""
        self._attempts = 0
        self._recorded_requests.clear()
