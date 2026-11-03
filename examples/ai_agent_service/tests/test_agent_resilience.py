"""
Resilience & Chaos Tests for FastAPI AI Agent Service using RetryLab.
"""

import pytest
from fastapi import HTTPException

from examples.ai_agent_service.app import ChatRequest, chat_endpoint, call_openai_with_resilience
from retrylab import FaultType, simulate_fault


def test_agent_survives_openai_429_rate_limit():
    # Inject 429 Rate Limit on first attempt, then recover on second attempt
    with simulate_fault(
        target="https://api.openai.com/v1/*",
        fault=FaultType.RATE_LIMIT_429,
        retry_after=1,
        fail_count=1,
        body='{"choices": [{"message": {"content": "Hello from resilient AI agent!"}}]}',
    ) as scenario:
        response = chat_endpoint(ChatRequest(prompt="Explain quantum computing", max_retries=3))

        assert response.attempts_made == 2
        assert "resilient AI agent" in response.response
        assert scenario.total_attempts == 2


def test_agent_survives_openai_timeout():
    # Inject Timeout on first attempt, then recover on second attempt
    with simulate_fault(
        target="https://api.openai.com/v1/*",
        fault=FaultType.TIMEOUT,
        fail_count=1,
        body='{"choices": [{"message": {"content": "Recovered after network timeout."}}]}',
    ) as scenario:
        response = chat_endpoint(ChatRequest(prompt="Summarize quarterly report", max_retries=3))

        assert response.attempts_made == 2
        assert "Recovered after network timeout" in response.response


def test_agent_fails_gracefully_when_retries_exhausted():
    # Inject 5 consecutive 503 Service Unavailable faults
    with simulate_fault(
        target="https://api.openai.com/v1/*",
        fault=FaultType.SERVICE_UNAVAILABLE_503,
        fail_count=5,
    ) as scenario:
        with pytest.raises(HTTPException) as exc_info:
            chat_endpoint(ChatRequest(prompt="Translate text", max_retries=2))

        assert exc_info.value.status_code == 504
        assert "OpenAI upstream failed after 2 attempts" in exc_info.value.detail
        assert scenario.total_attempts == 2
