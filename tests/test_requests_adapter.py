"""
Tests for RetryLabAdapter with requests.Session.
"""

import pytest
import requests
from retrylab import FaultScenario, FaultType, RetryLabAdapter


def test_requests_timeout_simulation():
    scenario = FaultScenario(
        target="https://api.stripe.com/v1/charges",
        fault=FaultType.TIMEOUT,
        fail_count=1,
    )
    adapter = RetryLabAdapter(scenario=scenario)
    session = requests.Session()
    session.mount("https://api.stripe.com", adapter)

    # First attempt should raise ReadTimeout
    with pytest.raises(requests.exceptions.ReadTimeout):
        session.post("https://api.stripe.com/v1/charges", json={"amount": 2000})

    # Second attempt should recover (200 OK)
    resp = session.post("https://api.stripe.com/v1/charges", json={"amount": 2000})
    assert resp.status_code == 200
    assert resp.json()["status"] == "recovered"
    assert scenario.total_attempts == 2


def test_requests_rate_limit_429():
    scenario = FaultScenario(
        target="https://api.openai.com/v1/*",
        fault=FaultType.RATE_LIMIT_429,
        retry_after_seconds=4,
        fail_count=1,
    )
    adapter = RetryLabAdapter(scenario=scenario)
    session = requests.Session()
    session.mount("https://api.openai.com", adapter)

    # First attempt -> 429
    resp1 = session.post("https://api.openai.com/v1/chat/completions", json={"prompt": "test"})
    assert resp1.status_code == 429
    assert resp1.headers["Retry-After"] == "4"
    assert resp1.json()["error"]["type"] == "rate_limit_exceeded"

    # Second attempt -> 200
    resp2 = session.post("https://api.openai.com/v1/chat/completions", json={"prompt": "test"})
    assert resp2.status_code == 200


def test_requests_server_error_500():
    scenario = FaultScenario(
        target="https://api.github.com/*",
        fault=FaultType.SERVER_ERROR_500,
        fail_count=1,
    )
    adapter = RetryLabAdapter(scenario=scenario)
    session = requests.Session()
    session.mount("https://api.github.com", adapter)

    resp = session.get("https://api.github.com/user/repos")
    assert resp.status_code == 500
    assert resp.json()["error"] == "Internal Server Error"


def test_requests_connection_error():
    scenario = FaultScenario(
        target="https://api.unreliable.io/*",
        fault=FaultType.CONNECTION_RESET,
        fail_count=1,
    )
    adapter = RetryLabAdapter(scenario=scenario)
    session = requests.Session()
    session.mount("https://api.unreliable.io", adapter)

    with pytest.raises(requests.exceptions.ConnectionError):
        session.get("https://api.unreliable.io/ping")
