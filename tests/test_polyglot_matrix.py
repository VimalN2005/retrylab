"""
Tests for PolyglotChaosMatrix and cross-SDK compatibility schema verification.
"""

from retrylab.matrix import PolyglotChaosMatrix, PolyglotScenarioSchema


def test_polyglot_matrix_valid_scenario():
    scenario = PolyglotScenarioSchema(
        name="stripe_rate_limit",
        url_pattern="api.stripe.com",
        method="POST",
        fault="http_status",
        fail_count=2,
        status_code=429,
        response_body={"error": "rate_limit_exceeded"},
        delay_ms=100,
        recover_status=200,
        recover_body={"id": "ch_123", "status": "succeeded"},
    )

    valid, violations = PolyglotChaosMatrix.verify_compatibility(scenario)
    assert valid is True
    assert len(violations) == 0


def test_polyglot_matrix_invalid_fault():
    scenario = PolyglotScenarioSchema(
        name="bad_fault",
        url_pattern="api.example.com",
        fault="unsupported_quantum_disruption",
        fail_count=0,  # Also invalid
    )

    valid, violations = PolyglotChaosMatrix.verify_compatibility(scenario)
    assert valid is False
    assert any("unsupported_quantum_disruption" in v for v in violations)
    assert any("fail_count must be at least 1" in v for v in violations)


def test_polyglot_matrix_to_go_snippet():
    scenario = PolyglotScenarioSchema(
        name="openai_rate_limit",
        url_pattern="api.openai.com",
        method="POST",
        fault="http_status",
        fail_count=3,
        status_code=429,
        response_body={"error": "rate_limit_exceeded"},
        delay_ms=50,
    )

    snippet = PolyglotChaosMatrix.to_go_snippet(scenario)
    assert "retrylab.Scenario{" in snippet
    assert 'Name:          "openai_rate_limit"' in snippet
    assert "Fault:         retrylab.FaultHTTPStatus" in snippet
    assert "FailCount:     3" in snippet
    assert "StatusCode:    429" in snippet
    assert "50 * time.Millisecond" in snippet


def test_polyglot_matrix_to_ts_snippet():
    scenario = PolyglotScenarioSchema(
        name="openai_rate_limit",
        url_pattern="api.openai.com",
        method="POST",
        fault="http_status",
        fail_count=3,
        status_code=429,
        response_body={"error": "rate_limit_exceeded"},
        delay_ms=50,
    )

    snippet = PolyglotChaosMatrix.to_ts_snippet(scenario)
    assert "const scenario: Scenario = {" in snippet
    assert 'name: "openai_rate_limit"' in snippet
    assert 'fault: "http_status"' in snippet
    assert "failCount: 3" in snippet
    assert "statusCode: 429" in snippet
    assert "delayMs: 50" in snippet
