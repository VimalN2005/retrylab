"""
RetryLab Circuit Breaker & Fail-Fast Resilience Pattern Auditor.
Verifies that applications trip their circuit breakers to avoid cascading upstream failures.
"""

from __future__ import annotations

from enum import Enum
from typing import Any
from pydantic import BaseModel, Field

from retrylab.exceptions import RecoveryAssertionError
from retrylab.models import FaultScenario, RecordedRequest
from retrylab.scenarios.sequential import SequentialScenario


class CircuitBreakerViolationType(str, Enum):
    """Categories of circuit breaker misconfigurations or failures."""

    CIRCUIT_FAILED_TO_TRIP = "circuit_failed_to_trip"
    PREMATURE_RETRY_DURING_OPEN_STATE = "premature_retry_during_open_state"
    NO_CIRCUIT_COOL_DOWN = "no_circuit_cool_down"


class CircuitBreakerViolation(BaseModel):
    """Details of an observed circuit breaker failure."""

    violation_type: CircuitBreakerViolationType
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class CircuitBreakerAuditor:
    """
    Audits an application's outbound request stream to ensure it tripped its circuit breaker
    and stopped hammering the failed dependency.
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        cooldown_seconds: float = 1.0,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds

    def audit(
        self,
        scenario: FaultScenario | SequentialScenario,
    ) -> list[CircuitBreakerViolation]:
        """
        Inspects recorded requests to detect whether the client continued making outbound calls
        after the failure threshold was exceeded, violating fail-fast principles.
        """
        records: list[RecordedRequest] = scenario.recorded_requests
        if len(records) <= self.failure_threshold:
            return []  # Not enough requests to trip the threshold

        violations: list[CircuitBreakerViolation] = []

        consecutive_faults = 0
        trip_index: int | None = None

        for idx, rec in enumerate(records):
            if rec.was_fault_injected:
                consecutive_faults += 1
                if consecutive_faults == self.failure_threshold and trip_index is None:
                    trip_index = idx
            else:
                consecutive_faults = 0

        # If threshold was hit, verify that subsequent calls were blocked until cooldown
        if trip_index is not None and trip_index < len(records) - 1:
            trip_time = records[trip_index].timestamp
            # Inspect subsequent requests
            for post_idx, post_rec in enumerate(records[trip_index + 1:], start=trip_index + 2):
                elapsed_since_trip = post_rec.timestamp - trip_time
                if elapsed_since_trip < self.cooldown_seconds:
                    violations.append(
                        CircuitBreakerViolation(
                            violation_type=CircuitBreakerViolationType.CIRCUIT_FAILED_TO_TRIP,
                            message=(
                                f"Attempt #{post_idx} reached upstream API only "
                                f"{elapsed_since_trip*1000:.1f}ms after threshold ({self.failure_threshold} failures). "
                                f"Circuit breaker should have tripped OPEN and failed fast for at least {self.cooldown_seconds}s."
                            ),
                            details={
                                "attempt": post_idx,
                                "elapsed_seconds": elapsed_since_trip,
                                "cooldown_required": self.cooldown_seconds,
                            },
                        )
                    )
                    break

        return violations

    def assert_tripped(self, scenario: FaultScenario | SequentialScenario) -> None:
        """
        Raises RecoveryAssertionError if the circuit breaker failed to trip after threshold.
        """
        violations = self.audit(scenario)
        if violations:
            summary = "\n".join(f"  - [{v.violation_type.value}] {v.message}" for v in violations)
            raise RecoveryAssertionError(
                f"Circuit breaker audit failed ({len(violations)} violation(s)):\n{summary}"
            )
