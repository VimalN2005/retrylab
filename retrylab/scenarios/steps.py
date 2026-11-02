"""
RetryLab Scenario Step Definitions.
Allows defining step-by-step stateful fault transitions (e.g. Timeout -> 503 -> 429 -> 200).
"""

from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, Field

from retrylab.models import FaultType


class StepKind(str, Enum):
    """The nature of the action in a scenario step."""

    FAULT = "fault"
    RECOVER = "recover"
    PASSTHROUGH = "passthrough"


class ScenarioStep(BaseModel):
    """
    A single step in a multi-step resilience scenario.

    Attributes:
        kind: Action kind (FAULT, RECOVER, PASSTHROUGH)
        fault_type: Type of fault (TIMEOUT, RATE_LIMIT_429, etc.) if kind is FAULT
        status_code: HTTP status code to return (defaults to fault or recover default)
        delay_seconds: Artificial delay to introduce before responding or timing out
        retry_after_seconds: Value for 'Retry-After' header in 429/503 responses
        headers: Custom response headers
        body: Custom response body string
        repeat: Number of matching requests that will execute this step before advancing
    """

    kind: StepKind = StepKind.FAULT
    fault_type: FaultType = FaultType.SERVER_ERROR_500
    status_code: int | None = None
    delay_seconds: float = Field(default=0.0, ge=0.0)
    retry_after_seconds: int = Field(default=2, ge=0)
    headers: dict[str, str] = Field(default_factory=dict)
    body: str | None = None
    repeat: int = Field(default=1, ge=1)
