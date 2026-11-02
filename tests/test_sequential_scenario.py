"""
Tests for Multi-Step SequentialScenario progression.
"""

import httpx
import pytest
import requests

from retrylab import (
    FaultType,
    RetryLabAdapter,
    RetryLabTransport,
    ScenarioStep,
    SequentialScenario,
    StepKind,
)


def test_sequential_scenario_httpx_progression():
    # Sequence:
    # 1. Timeout (attempt 1)
    # 2. HTTP 503 Service Unavailable (attempt 2)
    # 3. HTTP 200 Recover (attempt 3)
    scenario = SequentialScenario(
        name="multi_stage_outage",
        target="https://api.openai.com/v1/*",
        steps=[
            ScenarioStep(kind=StepKind.FAULT, fault_type=FaultType.TIMEOUT, repeat=1),
            ScenarioStep(
                kind=StepKind.FAULT,
                fault_type=FaultType.SERVICE_UNAVAILABLE_503,
                retry_after_seconds=5,
                repeat=1,
            ),
            ScenarioStep(
                kind=StepKind.RECOVER,
                status_code=200,
                body='{"status": "recovered", "model": "gpt-4o"}',
                repeat=1,
            ),
        ],
    )
    transport = RetryLabTransport(scenario=scenario)

    with httpx.Client(transport=transport) as client:
        # Attempt 1 -> ReadTimeout
        with pytest.raises(httpx.ReadTimeout):
            client.post("https://api.openai.com/v1/chat/completions", json={"prompt": "hi"})

        # Attempt 2 -> 503 Service Unavailable
        resp2 = client.post("https://api.openai.com/v1/chat/completions", json={"prompt": "hi"})
        assert resp2.status_code == 503
        assert resp2.headers["Retry-After"] == "5"

        # Attempt 3 -> 200 Recovered
        resp3 = client.post("https://api.openai.com/v1/chat/completions", json={"prompt": "hi"})
        assert resp3.status_code == 200
        assert resp3.json()["status"] == "recovered"

        # Attempt 4 -> Repeats last step (200 Recovered)
        resp4 = client.post("https://api.openai.com/v1/chat/completions", json={"prompt": "hi"})
        assert resp4.status_code == 200

    assert scenario.total_attempts == 4
    assert len(scenario.recorded_requests) == 4


def test_sequential_scenario_requests_progression():
    scenario = SequentialScenario(
        name="requests_sequence",
        target="https://api.stripe.com/v1/charges",
        steps=[
            ScenarioStep(kind=StepKind.FAULT, fault_type=FaultType.RATE_LIMIT_429, repeat=2),
            ScenarioStep(
                kind=StepKind.RECOVER,
                status_code=200,
                body='{"paid": true}',
            ),
        ],
    )
    adapter = RetryLabAdapter(scenario=scenario)
    session = requests.Session()
    session.mount("https://api.stripe.com", adapter)

    # Attempt 1 -> 429
    r1 = session.post("https://api.stripe.com/v1/charges")
    assert r1.status_code == 429

    # Attempt 2 -> 429 (repeat was 2)
    r2 = session.post("https://api.stripe.com/v1/charges")
    assert r2.status_code == 429

    # Attempt 3 -> 200 Recovered
    r3 = session.post("https://api.stripe.com/v1/charges")
    assert r3.status_code == 200
    assert r3.json()["paid"] is True


def test_sequential_scenario_reset():
    scenario = SequentialScenario(
        target="https://api.example.com/*",
        steps=[
            ScenarioStep(kind=StepKind.FAULT, fault_type=FaultType.TIMEOUT),
            ScenarioStep(kind=StepKind.RECOVER, status_code=200),
        ],
    )
    assert scenario.get_current_step().kind == StepKind.FAULT
    scenario.record_attempt(
        url="https://api.example.com/test",
        method="GET",
        headers={},
        body=b"",
        injected=True,
    )
    assert scenario.get_current_step().kind == StepKind.RECOVER

    # After reset, returns to initial step
    scenario.reset()
    assert scenario.total_attempts == 0
    assert scenario.get_current_step().kind == StepKind.FAULT
