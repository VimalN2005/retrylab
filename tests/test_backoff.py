"""
Tests for BackoffAuditor and retry budget assertion engine.
"""

import time
import httpx
import pytest

from retrylab import (
    BackoffAuditor,
    BackoffViolationType,
    FaultScenario,
    FaultType,
    RecoveryAssertionError,
    RetryLabTransport,
)


def test_backoff_clean_retries():
    scenario = FaultScenario(
        target="https://api.openai.com/v1/*",
        fault=FaultType.RATE_LIMIT_429,
        fail_count=2,
    )
    transport = RetryLabTransport(scenario=scenario)
    auditor = BackoffAuditor(max_attempts=3, min_interval_seconds=0.01)

    with httpx.Client(transport=transport) as client:
        # Attempt 1
        client.post("https://api.openai.com/v1/chat")
        time.sleep(0.02)
        # Attempt 2
        client.post("https://api.openai.com/v1/chat")
        time.sleep(0.02)
        # Attempt 3 (Recovered)
        client.post("https://api.openai.com/v1/chat")

    violations = auditor.audit(scenario)
    assert len(violations) == 0
    auditor.assert_backoff(scenario)


def test_backoff_exceeded_max_attempts():
    scenario = FaultScenario(
        target="https://api.example.com/*",
        fault=FaultType.TIMEOUT,
        fail_count=5,
    )
    transport = RetryLabTransport(scenario=scenario)
    auditor = BackoffAuditor(max_attempts=2)

    with httpx.Client(transport=transport) as client:
        for _ in range(3):
            try:
                client.get("https://api.example.com/data")
            except httpx.ReadTimeout:
                pass

    violations = auditor.audit(scenario)
    assert any(v.violation_type == BackoffViolationType.EXCEEDED_MAX_ATTEMPTS for v in violations)

    with pytest.raises(RecoveryAssertionError, match="exceeding the allowed maximum of 2"):
        auditor.assert_backoff(scenario)


def test_backoff_busy_loop_spam():
    scenario = FaultScenario(
        target="https://api.example.com/*",
        fault=FaultType.SERVER_ERROR_500,
        fail_count=2,
    )
    transport = RetryLabTransport(scenario=scenario)
    # Require at least 50ms between retries
    auditor = BackoffAuditor(min_interval_seconds=0.05)

    with httpx.Client(transport=transport) as client:
        # Trigger immediate consecutive calls with ~0ms sleep
        client.get("https://api.example.com/data")
        client.get("https://api.example.com/data")

    violations = auditor.audit(scenario)
    assert any(v.violation_type == BackoffViolationType.BUSY_LOOP_SPAM for v in violations)


def test_backoff_exceeded_total_duration():
    scenario = FaultScenario(
        target="https://api.example.com/*",
        fault=FaultType.RATE_LIMIT_429,
        fail_count=1,
    )
    transport = RetryLabTransport(scenario=scenario)
    # Total budget 0.05s
    auditor = BackoffAuditor(max_total_duration=0.05)

    with httpx.Client(transport=transport) as client:
        client.get("https://api.example.com/data")
        time.sleep(0.08)  # Exceeds total budget
        client.get("https://api.example.com/data")

    violations = auditor.audit(scenario)
    assert any(v.violation_type == BackoffViolationType.EXCEEDED_TIME_BUDGET for v in violations)
