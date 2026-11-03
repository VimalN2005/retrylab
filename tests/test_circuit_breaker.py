"""
Tests for CircuitBreakerAuditor pattern verification.
"""

import time
import httpx
import pytest

from retrylab import (
    CircuitBreakerAuditor,
    CircuitBreakerViolationType,
    FaultScenario,
    FaultType,
    RecoveryAssertionError,
    RetryLabTransport,
)


def test_circuit_breaker_properly_trips():
    scenario = FaultScenario(
        target="https://api.external.com/*",
        fault=FaultType.SERVER_ERROR_500,
        fail_count=5,
    )
    transport = RetryLabTransport(scenario=scenario)
    auditor = CircuitBreakerAuditor(failure_threshold=3, cooldown_seconds=0.1)

    # Simulated client with circuit breaker logic:
    # After 3 errors, client trips OPEN and stops calling upstream
    consecutive_errors = 0
    is_circuit_open = False

    with httpx.Client(transport=transport) as client:
        for _ in range(10):
            if is_circuit_open:
                # Client fails fast locally without calling client.get!
                continue

            resp = client.get("https://api.external.com/status")
            if resp.status_code >= 500:
                consecutive_errors += 1
                if consecutive_errors >= 3:
                    is_circuit_open = True

    # Upstream only saw 3 failed requests; remaining 7 were failed fast!
    assert scenario.total_attempts == 3
    violations = auditor.audit(scenario)
    assert len(violations) == 0
    auditor.assert_tripped(scenario)


def test_circuit_breaker_failed_to_trip_violation():
    scenario = FaultScenario(
        target="https://api.external.com/*",
        fault=FaultType.SERVER_ERROR_500,
        fail_count=10,
    )
    transport = RetryLabTransport(scenario=scenario)
    auditor = CircuitBreakerAuditor(failure_threshold=3, cooldown_seconds=0.5)

    # Buggy client with NO circuit breaker: keeps hammering upstream during 500 outage
    with httpx.Client(transport=transport) as client:
        for _ in range(5):
            client.get("https://api.external.com/status")
            time.sleep(0.01)

    violations = auditor.audit(scenario)
    assert len(violations) == 1
    assert violations[0].violation_type == CircuitBreakerViolationType.CIRCUIT_FAILED_TO_TRIP

    with pytest.raises(RecoveryAssertionError, match="Circuit breaker should have tripped OPEN"):
        auditor.assert_tripped(scenario)
