"""
Tests for YAML Scenario loading and validation.
"""

from pathlib import Path
import httpx
import pytest

from retrylab import (
    FaultScenario,
    FaultType,
    RetryLabTransport,
    ScenarioStep,
    SequentialScenario,
    StepKind,
    load_scenario_from_yaml,
    load_scenarios_from_dir,
)
from retrylab.exceptions import ScenarioValidationError


def test_load_single_fault_yaml():
    yaml_text = """
    name: openai_test
    target: "https://api.openai.com/v1/*"
    method: POST
    fault: rate_limit_429
    fail_count: 2
    retry_after: 3
    body: '{"error": "rate_limited"}'
    """
    scenario = load_scenario_from_yaml(yaml_text)
    assert isinstance(scenario, FaultScenario)
    assert scenario.name == "openai_test"
    assert scenario.target == "https://api.openai.com/v1/*"
    assert scenario.method == "POST"
    assert scenario.fault == FaultType.RATE_LIMIT_429
    assert scenario.fail_count == 2
    assert scenario.retry_after_seconds == 3


def test_load_multi_step_sequential_yaml():
    yaml_text = """
    name: multi_step_test
    match:
      url: "https://api.stripe.com/v1/*"
      method: POST
    steps:
      - kind: fault
        type: timeout
        delay: 50ms
        repeat: 1
      - kind: fault
        type: service_unavailable_503
        retry_after: 5
      - kind: recover
        code: 200
        body: '{"charge": "ok"}'
    """
    scenario = load_scenario_from_yaml(yaml_text)
    assert isinstance(scenario, SequentialScenario)
    assert scenario.name == "multi_step_test"
    assert scenario.target == "https://api.stripe.com/v1/*"
    assert scenario.method == "POST"
    assert len(scenario.steps) == 3
    assert scenario.steps[0].fault_type == FaultType.TIMEOUT
    assert scenario.steps[0].delay_seconds == 0.05
    assert scenario.steps[1].fault_type == FaultType.SERVICE_UNAVAILABLE_503
    assert scenario.steps[2].kind == StepKind.RECOVER


def test_load_from_file_and_execute():
    file_path = Path("examples/scenarios/stripe_outage.yaml")
    scenario = load_scenario_from_yaml(file_path)

    assert isinstance(scenario, SequentialScenario)
    assert scenario.name == "stripe_payment_resilience"

    transport = RetryLabTransport(scenario=scenario)
    with httpx.Client(transport=transport) as client:
        # Step 1: timeout
        with pytest.raises(httpx.ReadTimeout):
            client.post("https://api.stripe.com/v1/charges")

        # Step 2: 503
        r2 = client.post("https://api.stripe.com/v1/charges")
        assert r2.status_code == 503
        assert r2.headers["Retry-After"] == "3"

        # Step 3: 200 recovered
        r3 = client.post("https://api.stripe.com/v1/charges")
        assert r3.status_code == 200
        assert r3.json()["status"] == "succeeded"


def test_load_scenarios_from_dir():
    scenarios = load_scenarios_from_dir("examples/scenarios")
    assert len(scenarios) >= 2
    assert "stripe_payment_resilience" in scenarios
    assert "openai_rate_limit_demo" in scenarios


def test_yaml_validation_missing_target():
    invalid_yaml = """
    name: no_target
    fault: timeout
    """
    with pytest.raises(ScenarioValidationError, match="Missing required 'target'"):
        load_scenario_from_yaml(invalid_yaml)
