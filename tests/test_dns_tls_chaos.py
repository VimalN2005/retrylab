"""
Tests for DNS Resolution Failure and SSL/TLS Certificate Chaos Simulation.
"""

import socket
import ssl
import httpx
import pytest
import requests

from retrylab.adapters.requests_adapter import RetryLabAdapter
from retrylab.models import FaultScenario, FaultType
from retrylab.transport import RetryLabTransport


def test_httpx_dns_failure_and_recovery():
    """Verify DNS resolution failure (NXDOMAIN / socket.gaierror) and eventual recovery."""
    scenario = FaultScenario(
        name="dns_outage_simulation",
        target="https://api.payment-gateway.internal/v1/*",
        fault=FaultType.DNS_FAILURE,
        fail_count=1,
    )

    transport = RetryLabTransport(scenario=scenario)
    with httpx.Client(transport=transport) as client:
        # Attempt 1 -> Injected DNS failure (NXDOMAIN)
        with pytest.raises(httpx.ConnectError) as exc_info:
            client.get("https://api.payment-gateway.internal/v1/charge")

        assert "DNS resolution failure" in str(exc_info.value)
        assert isinstance(exc_info.value.__cause__, socket.gaierror)

        # Attempt 2 -> Clean recovery after DNS cache refresh or backoff
        resp = client.get("https://api.payment-gateway.internal/v1/charge")
        assert resp.status_code == 200
        assert resp.json()["status"] == "recovered"


def test_httpx_dns_timeout():
    """Verify DNS resolution query timeout simulation."""
    scenario = FaultScenario(
        name="dns_timeout_simulation",
        target="https://api.external.com/*",
        fault=FaultType.DNS_TIMEOUT,
        fail_count=1,
    )

    transport = RetryLabTransport(scenario=scenario)
    with httpx.Client(transport=transport) as client:
        with pytest.raises(httpx.ConnectTimeout) as exc_info:
            client.get("https://api.external.com/data")

        assert "DNS resolution timeout" in str(exc_info.value)


def test_httpx_tls_handshake_timeout():
    """Verify TLS handshake negotiation stall / timeout simulation."""
    scenario = FaultScenario(
        name="tls_handshake_timeout",
        target="https://api.secure-vault.com/*",
        fault=FaultType.TLS_HANDSHAKE_TIMEOUT,
        fail_count=1,
    )

    transport = RetryLabTransport(scenario=scenario)
    with httpx.Client(transport=transport) as client:
        with pytest.raises(httpx.ConnectTimeout) as exc_info:
            client.post("https://api.secure-vault.com/keys")

        assert "TLS handshake timeout" in str(exc_info.value)


def test_httpx_ssl_cert_verification_failed():
    """Verify SSL certificate expiration or invalid CA chain simulation."""
    scenario = FaultScenario(
        name="expired_cert_simulation",
        target="https://expired.badssl.com/*",
        fault=FaultType.SSL_CERT_VERIFICATION_FAILED,
        fail_count=1,
    )

    transport = RetryLabTransport(scenario=scenario)
    with httpx.Client(transport=transport) as client:
        with pytest.raises(httpx.ConnectError) as exc_info:
            client.get("https://expired.badssl.com/resource")

        assert "CERTIFICATE_VERIFY_FAILED" in str(exc_info.value)
        assert isinstance(exc_info.value.__cause__, ssl.SSLError)


def test_httpx_ssl_hostname_mismatch():
    """Verify TLS certificate hostname mismatch verification."""
    scenario = FaultScenario(
        name="hostname_mismatch_simulation",
        target="https://wrong.host.badssl.com/*",
        fault=FaultType.SSL_HOSTNAME_MISMATCH,
        fail_count=1,
    )

    transport = RetryLabTransport(scenario=scenario)
    with httpx.Client(transport=transport) as client:
        with pytest.raises(httpx.ConnectError) as exc_info:
            client.get("https://wrong.host.badssl.com/resource")

        assert "hostname mismatch" in str(exc_info.value).lower()


def test_requests_adapter_dns_and_ssl_faults():
    """Verify Requests Session adapter correctly handles DNS and SSL chaos injection."""
    # 1. DNS Failure in Requests
    dns_scenario = FaultScenario(
        name="requests_dns_chaos",
        target="https://api.stripe.com/v1/customers",
        fault=FaultType.DNS_FAILURE,
        fail_count=1,
    )

    session = requests.Session()
    session.mount("https://api.stripe.com", RetryLabAdapter(scenario=dns_scenario))

    with pytest.raises(requests.exceptions.ConnectionError) as exc_info:
        session.get("https://api.stripe.com/v1/customers")

    assert isinstance(exc_info.value.__cause__, socket.gaierror)

    # Attempt 2 -> Recovered
    resp = session.get("https://api.stripe.com/v1/customers")
    assert resp.status_code == 200

    # 2. SSL Verification Failure in Requests
    ssl_scenario = FaultScenario(
        name="requests_ssl_chaos",
        target="https://api.github.com/*",
        fault=FaultType.SSL_CERT_VERIFICATION_FAILED,
        fail_count=1,
    )
    session_ssl = requests.Session()
    session_ssl.mount("https://api.github.com", RetryLabAdapter(scenario=ssl_scenario))

    with pytest.raises(requests.exceptions.SSLError):
        session_ssl.get("https://api.github.com/user")
