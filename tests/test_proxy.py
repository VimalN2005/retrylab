"""
Tests for RetryLab HTTP Proxy Server.
"""

import json
import sys
import urllib.error
import urllib.request
import pytest

from retrylab.models import FaultScenario, FaultType
from retrylab.proxy.server import create_proxy_server, start_background_proxy


def test_create_proxy_server_binding():
    scenario = FaultScenario(
        name="test_bind",
        target="http://example.com/*",
        fault=FaultType.TIMEOUT,
    )
    # Testing server instance creation and scenario attachment
    server = create_proxy_server(scenario, host="127.0.0.1", port=0)
    assert server is not None
    assert server.RequestHandlerClass.scenario.name == "test_bind"
    server.server_close()


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="Windows sandbox restricts local socket access; runs in Linux CI environment",
)
def test_proxy_server_health_and_report():
    scenario = FaultScenario(
        name="proxy_test",
        target="http://localhost*",
        fault=FaultType.RATE_LIMIT_429,
        retry_after_seconds=3,
        fail_count=1,
    )
    server, thread, server_url = start_background_proxy(scenario, host="127.0.0.1", port=0)

    try:
        # 1. Health check
        with urllib.request.urlopen(f"{server_url}/_retrylab/health") as resp:
            data = json.loads(resp.read().decode())
            assert data["status"] == "ok"
            assert data["scenario"] == "proxy_test"

        # 2. First request to target -> 429
        try:
            urllib.request.urlopen(f"{server_url}/v1/chat")
            pytest.fail("Expected 429 HTTPError")
        except urllib.error.HTTPError as err:
            assert err.code == 429
            assert err.headers.get("Retry-After") == "3"

        # 3. Second request to target -> 200 Recovered
        with urllib.request.urlopen(f"{server_url}/v1/chat") as resp:
            assert resp.code == 200
            data = json.loads(resp.read().decode())
            assert data["status"] == "recovered"

        # 4. Report endpoint
        with urllib.request.urlopen(f"{server_url}/_retrylab/report") as resp:
            report = json.loads(resp.read().decode())
            assert report["total_attempts"] == 2
            assert len(report["records"]) == 2

    finally:
        server.shutdown()
        server.server_close()
