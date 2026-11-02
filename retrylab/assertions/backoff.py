"""
RetryLab Exponential Backoff & Retry Budget Auditor.
Verifies that client retries implement responsible backoff, avoid thundering herds, and respect latency budgets.
"""

from __future__ import annotations

from enum import Enum
from typing import Any
from pydantic import BaseModel, Field

from retrylab.exceptions import RecoveryAssertionError
from retrylab.models import FaultScenario, RecordedRequest
from retrylab.scenarios.sequential import SequentialScenario


class BackoffViolationType(str, Enum):
    """Categories of retry backoff policy violations."""

    EXCEEDED_MAX_ATTEMPTS = "exceeded_max_attempts"
    EXCEEDED_TIME_BUDGET = "exceeded_time_budget"
    BUSY_LOOP_SPAM = "busy_loop_spam"
    BACKOFF_NOT_INCREASING = "backoff_not_increasing"


class BackoffViolation(BaseModel):
    """Details of an observed retry timing or budget violation."""

    violation_type: BackoffViolationType
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class BackoffAuditor:
    """
    Audits timing and intervals of retried requests in a FaultScenario or SequentialScenario.
    """

    def __init__(
        self,
        max_attempts: int | None = None,
        max_total_duration: float | None = None,
        min_interval_seconds: float = 0.05,
        enforce_exponential: bool = False,
    ) -> None:
        self.max_attempts = max_attempts
        self.max_total_duration = max_total_duration
        self.min_interval_seconds = min_interval_seconds
        self.enforce_exponential = enforce_exponential

    def audit(self, scenario: FaultScenario | SequentialScenario) -> list[BackoffViolation]:
        """
        Inspects timestamps and intervals across all recorded attempts in the scenario.
        Returns a list of any detected violations.
        """
        records: list[RecordedRequest] = scenario.recorded_requests
        if len(records) <= 1:
            return []  # Zero or one request; no retries to audit

        violations: list[BackoffViolation] = []
        total_attempts = len(records)

        # 1. Enforce Max Attempts Budget
        if self.max_attempts is not None and total_attempts > self.max_attempts:
            violations.append(
                BackoffViolation(
                    violation_type=BackoffViolationType.EXCEEDED_MAX_ATTEMPTS,
                    message=(
                        f"Client made {total_attempts} attempts, exceeding the allowed "
                        f"maximum of {self.max_attempts}."
                    ),
                    details={"total_attempts": total_attempts, "max_allowed": self.max_attempts},
                )
            )

        # Calculate time intervals between consecutive attempts
        intervals: list[float] = []
        for i in range(len(records) - 1):
            delta = records[i + 1].timestamp - records[i].timestamp
            intervals.append(max(0.0, delta))

        total_elapsed = records[-1].timestamp - records[0].timestamp

        # 2. Enforce Max Total Time Budget
        if self.max_total_duration is not None and total_elapsed > self.max_total_duration:
            violations.append(
                BackoffViolation(
                    violation_type=BackoffViolationType.EXCEEDED_TIME_BUDGET,
                    message=(
                        f"Total retry duration ({total_elapsed:.2f}s) exceeded the allowed "
                        f"budget of {self.max_total_duration:.2f}s."
                    ),
                    details={"total_elapsed": total_elapsed, "max_budget": self.max_total_duration},
                )
            )

        # 3. Check for Busy Loop / Zero-Delay Retry Spamming
        for idx, interval in enumerate(intervals, start=1):
            if interval < self.min_interval_seconds:
                violations.append(
                    BackoffViolation(
                        violation_type=BackoffViolationType.BUSY_LOOP_SPAM,
                        message=(
                            f"Attempt #{idx + 1} was triggered after only {interval*1000:.1f}ms "
                            f"(below threshold of {self.min_interval_seconds*1000:.1f}ms). "
                            "Clients must introduce backoff delays to prevent server DDoS."
                        ),
                        details={"attempt": idx + 1, "interval_seconds": interval},
                    )
                )

        # 4. Check for Exponential Increase
        if self.enforce_exponential and len(intervals) >= 2:
            for i in range(len(intervals) - 1):
                prev_interval = intervals[i]
                next_interval = intervals[i + 1]
                # Allow a small factor (0.9) to account for timer noise
                if next_interval < (prev_interval * 0.9):
                    violations.append(
                        BackoffViolation(
                            violation_type=BackoffViolationType.BACKOFF_NOT_INCREASING,
                            message=(
                                f"Backoff interval decreased from {prev_interval*1000:.1f}ms (retry #{i+1}) "
                                f"to {next_interval*1000:.1f}ms (retry #{i+2}). Backoff must increase progressively."
                            ),
                            details={"prev_interval": prev_interval, "next_interval": next_interval},
                        )
                    )

        return violations

    def assert_backoff(self, scenario: FaultScenario | SequentialScenario) -> None:
        """
        Raises RecoveryAssertionError if any backoff or budget violations are detected.
        """
        violations = self.audit(scenario)
        if violations:
            summary = "\n".join(f"  - [{v.violation_type.value}] {v.message}" for v in violations)
            raise RecoveryAssertionError(
                f"Backoff and retry budget audit failed ({len(violations)} violation(s)):\n{summary}"
            )
