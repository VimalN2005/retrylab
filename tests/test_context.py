"""
Tests for simulate_fault context manager and transparent client patching.
"""

import httpx
import pytest
import requests

from retrylab import (
    FaultType,
    ScenarioStep,
    SequentialScenario,
    StepKind,
    simulate_fault,
)


def test_simulate_fault_httpx_context():
    # Application code that creates a regular httpx.Client
    def fetch_user_data():
        with httpx.Client() as client:
            return client.get("https://api.github.com/users/octocat")

    with simulate_fault("https://api.github.com/*", fault="rate_limit_429", fail_count=1) as sc:
        # First call hits 429
        resp1 = fetch_user_data()
        assert resp1.status_code == 429

        # Second call recovers (200 OK)
        resp2 = fetch_user_data()
        assert resp2.status_code == 200

    assert sc.total_attempts == 2

    # Verify context cleaned up and original Client behavior restored
    clean_client = httpx.Client()
    assert clean_client._transport is not None
    clean_client.close()


def test_simulate_fault_requests_context():
    def submit_payment():
        session = requests.Session()
        return session.post("https://api.stripe.com/v1/charges", json={"amount": 100})

    with simulate_fault("https://api.stripe.com/v1/charges", fault="timeout", fail_count=1) as sc:
        # First call times out
        with pytest.raises(requests.exceptions.ReadTimeout):
            submit_payment()

        # Second call recovers
        resp = submit_payment()
        assert resp.status_code == 200

    assert sc.total_attempts == 2


def test_simulate_fault_with_sequential_scenario():
    scenario = SequentialScenario(
        target="https://api.openai.com/v1/*",
        steps=[
            ScenarioStep(kind=StepKind.FAULT, fault_type=FaultType.SERVICE_UNAVAILABLE_503),
            ScenarioStep(kind=StepKind.RECOVER, status_code=200, body='{"status": "ok"}'),
        ],
    )

    with simulate_fault(scenario):
        with httpx.Client() as client:
            r1 = client.post("https://api.openai.com/v1/chat")
            assert r1.status_code == 503

            r2 = client.post("https://api.openai.com/v1/chat")
            assert r2.status_code == 200
            assert r2.json()["status"] == "ok"
