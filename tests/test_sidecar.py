"""
Tests for RetryLab Chaos Sidecar Proxy (retrylab.sidecar).
"""

from __future__ import annotations

import io
import json
import sys
import urllib.request
import pytest

from retrylab.models import FaultScenario, FaultType
from retrylab.sidecar import (
    RetryLabSidecar,
    SidecarConfig,
    SidecarMetrics,
    SidecarProxyHandler,
    start_background_sidecar,
)


class DummySidecarHandler(SidecarProxyHandler):
    """In-process mock handler for testing sidecar routing without network socket constraints."""

    def __init__(self, method: str, path: str, headers: dict | None = None, body: bytes = b"", config: SidecarConfig | None = None):
        self.config = config or SidecarConfig()
        self.metrics = SidecarMetrics()
        self.scenario = self.config.scenario
        self.command = method
        self.path = path
        self.headers = headers or {}
        self.rfile = io.BytesIO(body)
        self.wfile = io.BytesIO()
        self.status_codes: list[int] = []
        self.sent_headers: dict[str, str] = {}

    def send_response(self, code: int, message: str | None = None) -> None:
        self.status_codes.append(code)

    def send_header(self, keyword: str, value: str) -> None:
        self.sent_headers[keyword] = str(value)

    def end_headers(self) -> None:
        pass


def test_sidecar_config_defaults_and_dict():
    """Verify SidecarConfig defaults and dictionary conversion."""
    cfg = SidecarConfig()
    assert cfg.host == "0.0.0.0"
    assert cfg.port == 8080
    assert cfg.target_upstream is None
    assert cfg.metrics_enabled is True
    assert cfg.cors_enabled is True

    d = cfg.to_dict()
    assert d["port"] == 8080
    assert d["cors_enabled"] is True


def test_sidecar_metrics_tracking():
    """Verify metrics calculation for faults and passthroughs."""
    metrics = SidecarMetrics()
    assert metrics.total_intercepted == 0
    assert metrics.uptime_seconds >= 0.0

    metrics.record_request("POST", 503, 14.5, was_fault=True)
    metrics.record_request("POST", 200, 8.2, was_fault=False)

    assert metrics.total_intercepted == 2
    assert metrics.faults_injected == 1
    assert metrics.passthroughs == 1
    assert metrics.requests_by_status[503] == 1
    assert metrics.requests_by_status[200] == 1
    assert metrics.requests_by_method["POST"] == 2

    d = metrics.to_dict()
    assert d["total_intercepted"] == 2
    assert d["average_latency_ms"] == 11.35


def test_sidecar_server_binding():
    """Verify sidecar server instantiates and binds to address."""
    cfg = SidecarConfig(host="127.0.0.1", port=0)
    sidecar = RetryLabSidecar(cfg)
    server = sidecar.create_server()
    assert server is not None
    assert server.server_address[0] == "127.0.0.1"
    assert sidecar.server_port > 0
    assert "127.0.0.1" in sidecar.server_url
    sidecar.stop()


def test_sidecar_health_and_metrics_endpoints():
    """Verify /_retrylab/health and /_retrylab/metrics in-process routing."""
    handler = DummySidecarHandler("GET", "/_retrylab/health")
    handler.do_GET()

    assert handler.status_codes[-1] == 200
    data = json.loads(handler.wfile.getvalue().decode("utf-8"))
    assert data["status"] == "UP"
    assert data["sidecar"] == "healthy"

    metrics_handler = DummySidecarHandler("GET", "/_retrylab/metrics")
    metrics_handler.do_GET()

    assert metrics_handler.status_codes[-1] == 200
    m_data = json.loads(metrics_handler.wfile.getvalue().decode("utf-8"))
    assert "metrics" in m_data
    assert "config" in m_data


def test_sidecar_fault_injection_and_recovery():
    """Verify sidecar injects 503 on attempt 1 and recovers on attempt 2."""
    scenario = FaultScenario(
        name="stripe_sidecar_test",
        target="*/v1/charges*",
        fault=FaultType.SERVICE_UNAVAILABLE_503,
        fail_count=1,
        custom_body=json.dumps({"error": "Stripe temporarily unavailable"}),
    )
    cfg = SidecarConfig(scenario=scenario)

    # Attempt 1: Injected 503
    h1 = DummySidecarHandler("POST", "/v1/charges", {"Host": "api.stripe.com"}, body=b'{"amount": 5000}', config=cfg)
    h1.do_POST()
    assert h1.status_codes[-1] == 503
    assert h1.sent_headers.get("X-RetryLab-Injected") == "true"
    body1 = json.loads(h1.wfile.getvalue().decode("utf-8"))
    assert "Stripe temporarily unavailable" in body1["error"]

    # Attempt 2: Recovered 200 pass-through
    h2 = DummySidecarHandler("POST", "/v1/charges", {"Host": "api.stripe.com"}, body=b'{"amount": 5000}', config=cfg)
    h2.do_POST()
    assert h2.status_codes[-1] == 200
    assert h2.sent_headers.get("X-RetryLab-Passthrough") == "true"
    body2 = json.loads(h2.wfile.getvalue().decode("utf-8"))
    assert "Pass-Through Success" in body2["message"]


def test_sidecar_cors_preflight():
    """Verify OPTIONS request returns 204 No Content with CORS headers."""
    handler = DummySidecarHandler("OPTIONS", "/api/v1/checkout", {"Origin": "http://localhost:3000"})
    handler.do_OPTIONS()

    assert handler.status_codes[-1] == 204
    assert handler.sent_headers.get("Access-Control-Allow-Origin") == "*"
    assert "GET, POST" in handler.sent_headers.get("Access-Control-Allow-Methods", "")


def test_sidecar_scenario_status_and_reset():
    """Verify /_retrylab/scenario and /_retrylab/reset endpoints."""
    scenario = FaultScenario(
        name="reset_test",
        target="*",
        fault=FaultType.RATE_LIMIT_429,
        fail_count=1,
    )
    cfg = SidecarConfig(scenario=scenario)

    # Check scenario endpoint
    h1 = DummySidecarHandler("GET", "/_retrylab/scenario", config=cfg)
    h1.do_GET()
    assert h1.status_codes[-1] == 200
    data = json.loads(h1.wfile.getvalue().decode("utf-8"))
    assert data["scenario"] == "reset_test"

    # Reset scenario
    h2 = DummySidecarHandler("POST", "/_retrylab/reset", config=cfg)
    h2.do_POST()
    assert h2.status_codes[-1] == 200
    r_data = json.loads(h2.wfile.getvalue().decode("utf-8"))
    assert r_data["status"] == "reset"


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="Windows sandbox restricts local socket access; runs in Linux CI environment",
)
def test_sidecar_live_socket_communication():
    """Verify live HTTP communication against background sidecar proxy in CI."""
    cfg = SidecarConfig(host="127.0.0.1", port=0)
    sidecar, _ = start_background_sidecar(cfg)
    try:
        with urllib.request.urlopen(f"{sidecar.server_url}/_retrylab/health", timeout=3.0) as resp:
            assert resp.getcode() == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data["status"] == "UP"
    finally:
        sidecar.stop()
