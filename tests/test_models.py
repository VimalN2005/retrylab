"""
Tests for RetryLab Pydantic models and matching logic.
"""

import pytest
from retrylab.models import FaultScenario, FaultType


def test_scenario_url_matching_exact():
    scenario = FaultScenario(
        target="https://api.stripe.com/v1/charges",
        fault=FaultType.TIMEOUT,
    )
    assert scenario.matches("https://api.stripe.com/v1/charges", "POST")
    assert not scenario.matches("https://api.stripe.com/v1/refunds", "POST")


def test_scenario_url_matching_wildcard():
    scenario = FaultScenario(
        target="https://api.openai.com/v1/*",
        fault=FaultType.RATE_LIMIT_429,
    )
    assert scenario.matches("https://api.openai.com/v1/chat/completions", "POST")
    assert scenario.matches("https://api.openai.com/v1/embeddings", "POST")
    assert not scenario.matches("https://api.anthropic.com/v1/messages", "POST")


def test_scenario_method_filter():
    scenario = FaultScenario(
        target="https://api.stripe.com/v1/charges",
        fault=FaultType.SERVER_ERROR_500,
        method="POST",
    )
    assert scenario.matches("https://api.stripe.com/v1/charges", "POST")
    assert not scenario.matches("https://api.stripe.com/v1/charges", "GET")


def test_scenario_state_transition():
    scenario = FaultScenario(
        target="https://api.example.com/test",
        fault=FaultType.TIMEOUT,
        fail_count=2,
    )

    # Attempt 1 -> should fault
    assert scenario.should_inject_fault("https://api.example.com/test", "GET")
    scenario.record_attempt(
        url="https://api.example.com/test",
        method="GET",
        headers={},
        body=b"",
        injected=True,
    )
    assert scenario.total_attempts == 1

    # Attempt 2 -> should fault
    assert scenario.should_inject_fault("https://api.example.com/test", "GET")
    scenario.record_attempt(
        url="https://api.example.com/test",
        method="GET",
        headers={},
        body=b"",
        injected=True,
    )
    assert scenario.total_attempts == 2

    # Attempt 3 -> should NOT fault (recovered)
    assert not scenario.should_inject_fault("https://api.example.com/test", "GET")
    scenario.record_attempt(
        url="https://api.example.com/test",
        method="GET",
        headers={},
        body=b"",
        injected=False,
    )
    assert scenario.total_attempts == 3
    assert len(scenario.recorded_requests) == 3
    assert scenario.recorded_requests[0].was_fault_injected is True
    assert scenario.recorded_requests[2].was_fault_injected is False

    # Test reset
    scenario.reset()
    assert scenario.total_attempts == 0
    assert len(scenario.recorded_requests) == 0
