"""
Tests for RetryLab Pytest plugin fixtures.
"""

from retrylab.models import FaultScenario, FaultType


def test_retrylab_auditor_fixture(retrylab_auditor):
    assert retrylab_auditor.idempotency_header == "Idempotency-Key"


def test_make_fault_client_fixture(make_fault_client):
    scenario = FaultScenario(
        target="https://api.openai.com/*",
        fault=FaultType.RATE_LIMIT_429,
        fail_count=1,
    )
    client = make_fault_client(scenario)

    with client:
        resp = client.post("https://api.openai.com/v1/chat")
        assert resp.status_code == 429

        resp2 = client.post("https://api.openai.com/v1/chat")
        assert resp2.status_code == 200


def test_make_fault_session_fixture(make_fault_session):
    scenario = FaultScenario(
        target="https://api.stripe.com/v1/*",
        fault=FaultType.SERVER_ERROR_500,
        fail_count=1,
    )
    session = make_fault_session(scenario)

    resp = session.get("https://api.stripe.com/v1/charges")
    assert resp.status_code == 500
