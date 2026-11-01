"""
Tests for AsyncRetryLabTransport with httpx.AsyncClient.
"""

import sys
import httpx
import pytest
from retrylab import AsyncRetryLabTransport, FaultScenario, FaultType

pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="Windows sandbox restricts local socketpair; runs in Linux CI environment",
)


@pytest.mark.asyncio
async def test_async_transport_timeout_and_recovery():
    scenario = FaultScenario(
        target="https://api.openai.com/v1/*",
        fault=FaultType.TIMEOUT,
        fail_count=1,
    )
    transport = AsyncRetryLabTransport(scenario=scenario)

    async with httpx.AsyncClient(transport=transport) as client:
        # First async request should timeout
        with pytest.raises(httpx.ReadTimeout):
            await client.post("https://api.openai.com/v1/chat/completions", json={"prompt": "hi"})

        # Second async request should recover
        res = await client.post(
            "https://api.openai.com/v1/chat/completions", json={"prompt": "hi"}
        )
        assert res.status_code == 200
        assert res.json()["status"] == "recovered"

    assert scenario.total_attempts == 2


@pytest.mark.asyncio
async def test_async_transport_rate_limit():
    scenario = FaultScenario(
        target="https://api.anthropic.com/v1/*",
        fault=FaultType.RATE_LIMIT_429,
        retry_after_seconds=5,
        fail_count=1,
    )
    transport = AsyncRetryLabTransport(scenario=scenario)

    async with httpx.AsyncClient(transport=transport) as client:
        res1 = await client.post("https://api.anthropic.com/v1/messages", json={"text": "hello"})
        assert res1.status_code == 429
        assert res1.headers["Retry-After"] == "5"

        res2 = await client.post("https://api.anthropic.com/v1/messages", json={"text": "hello"})
        assert res2.status_code == 200
