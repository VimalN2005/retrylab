"""
Tests for synchronous RetryLabTransport.
"""

import httpx
import pytest
from retrylab import FaultScenario, FaultType, RetryLabTransport


def test_transport_timeout_simulation():
    scenario = FaultScenario(
        target="https://api.stripe.com/v1/charges",
        fault=FaultType.TIMEOUT,
        fail_count=1,
    )
    transport = RetryLabTransport(scenario=scenario)

    with httpx.Client(transport=transport) as client:
        # First request should timeout
        with pytest.raises(httpx.ReadTimeout):
            client.post("https://api.stripe.com/v1/charges", json={"amount": 1000})

        # Second request should recover (200 OK)
        response = client.post("https://api.stripe.com/v1/charges", json={"amount": 1000})
        assert response.status_code == 200
        assert response.json()["status"] == "recovered"

    # Verify recorded attempts
    assert scenario.total_attempts == 2
    assert scenario.recorded_requests[0].was_fault_injected is True
    assert scenario.recorded_requests[1].was_fault_injected is False


def test_transport_rate_limit_429():
    scenario = FaultScenario(
        target="https://api.openai.com/v1/*",
        fault=FaultType.RATE_LIMIT_429,
        retry_after_seconds=3,
        fail_count=1,
    )
    transport = RetryLabTransport(scenario=scenario)

    with httpx.Client(transport=transport) as client:
        # Attempt 1 -> 429 Rate Limit
        resp1 = client.post("https://api.openai.com/v1/chat/completions", json={"model": "gpt-4"})
        assert resp1.status_code == 429
        assert resp1.headers["Retry-After"] == "3"
        assert resp1.json()["error"]["type"] == "rate_limit_exceeded"

        # Attempt 2 -> 200 Recovered
        resp2 = client.post("https://api.openai.com/v1/chat/completions", json={"model": "gpt-4"})
        assert resp2.status_code == 200
        assert resp2.json()["status"] == "recovered"


def test_transport_500_server_error():
    scenario = FaultScenario(
        target="https://api.github.com/*",
        fault=FaultType.SERVER_ERROR_500,
        fail_count=1,
    )
    transport = RetryLabTransport(scenario=scenario)

    with httpx.Client(transport=transport) as client:
        res = client.get("https://api.github.com/user")
        assert res.status_code == 500
        assert res.json()["error"] == "Internal Server Error"


def test_transport_connection_reset():
    scenario = FaultScenario(
        target="https://api.database.internal/*",
        fault=FaultType.CONNECTION_RESET,
        fail_count=1,
    )
    transport = RetryLabTransport(scenario=scenario)

    with httpx.Client(transport=transport) as client:
        with pytest.raises(httpx.ConnectError):
            client.get("https://api.database.internal/health")


def test_transport_unmatched_url_passthrough():
    scenario = FaultScenario(
        target="https://api.stripe.com/*",
        fault=FaultType.TIMEOUT,
        fail_count=1,
    )
    transport = RetryLabTransport(scenario=scenario)

    with httpx.Client(transport=transport) as client:
        # Unmatched URL should not experience fault
        res = client.get("https://api.different-service.com/status")
        assert res.status_code == 200
        assert res.headers.get("X-RetryLab-Status") == "recovered"
