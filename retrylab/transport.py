"""
RetryLab HTTPX Transports for Sync and Async Interception.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any
import httpx

from retrylab.models import FaultScenario, FaultType


def _build_synthetic_response(
    request: httpx.Request,
    scenario: FaultScenario,
) -> httpx.Response:
    """Construct an HTTP response corresponding to the specified fault."""
    default_headers: dict[str, str] = {
        "Content-Type": "application/json",
        "X-Simulated-By": "RetryLab",
    }
    status_code: int = scenario.status_code or 500
    default_body: dict[str, Any] = {"error": "Simulated fault by RetryLab"}

    if scenario.fault == FaultType.RATE_LIMIT_429:
        status_code = scenario.status_code or 429
        default_headers["Retry-After"] = str(scenario.retry_after_seconds)
        default_body = {
            "error": {
                "type": "rate_limit_exceeded",
                "message": f"Rate limit exceeded. Retry after {scenario.retry_after_seconds}s.",
            }
        }
    elif scenario.fault == FaultType.SERVER_ERROR_500:
        status_code = scenario.status_code or 500
        default_body = {"error": "Internal Server Error"}
    elif scenario.fault == FaultType.BAD_GATEWAY_502:
        status_code = scenario.status_code or 502
        default_body = {"error": "Bad Gateway"}
    elif scenario.fault == FaultType.SERVICE_UNAVAILABLE_503:
        status_code = scenario.status_code or 503
        default_headers["Retry-After"] = str(scenario.retry_after_seconds)
        default_body = {"error": "Service Unavailable"}
    elif scenario.fault == FaultType.GATEWAY_TIMEOUT_504:
        status_code = scenario.status_code or 504
        default_body = {"error": "Gateway Timeout"}

    # Merge custom headers and custom body
    headers = {**default_headers, **scenario.custom_headers}
    content: bytes
    if scenario.custom_body is not None:
        content = scenario.custom_body.encode("utf-8")
    else:
        content = json.dumps(default_body).encode("utf-8")

    return httpx.Response(
        status_code=status_code,
        headers=headers,
        content=content,
        request=request,
    )


def _inject_transport_fault(scenario: FaultScenario, request: httpx.Request, url_str: str) -> None:
    """Raise simulated network, timeout, DNS, or TLS faults."""
    fault = scenario.fault
    if fault == FaultType.TIMEOUT:
        raise httpx.ReadTimeout(
            f"Simulated ReadTimeout for {url_str} by RetryLab",
            request=request,
        )

    if fault == FaultType.CONNECTION_RESET:
        raise httpx.ConnectError(
            f"Simulated Connection Reset for {url_str} by RetryLab",
            request=request,
        )

    if fault == FaultType.DNS_FAILURE:
        import socket
        exc = httpx.ConnectError(
            f"Simulated DNS resolution failure (NXDOMAIN) for {url_str} by RetryLab",
            request=request,
        )
        exc.__cause__ = socket.gaierror(-2, "Name or service not known")
        raise exc

    if fault == FaultType.DNS_TIMEOUT:
        raise httpx.ConnectTimeout(
            f"Simulated DNS resolution timeout for {url_str} by RetryLab",
            request=request,
        )

    if fault == FaultType.TLS_HANDSHAKE_TIMEOUT:
        raise httpx.ConnectTimeout(
            f"Simulated TLS handshake timeout during SSL negotiation for {url_str} by RetryLab",
            request=request,
        )

    if fault == FaultType.SSL_CERT_VERIFICATION_FAILED:
        import ssl
        exc = httpx.ConnectError(
            f"[SSL: CERTIFICATE_VERIFY_FAILED] Certificate verify failed for {url_str} by RetryLab",
            request=request,
        )
        try:
            exc.__cause__ = ssl.SSLCertVerificationError(1, "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: certificate has expired")
        except Exception:
            exc.__cause__ = ssl.SSLError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed")
        raise exc

    if fault == FaultType.SSL_HOSTNAME_MISMATCH:
        import ssl
        exc = httpx.ConnectError(
            f"[SSL: CERTIFICATE_VERIFY_FAILED] Certificate hostname mismatch for {url_str} by RetryLab",
            request=request,
        )
        try:
            exc.__cause__ = ssl.CertificateError(f"hostname '{request.url.host}' doesn't match certificate")
        except Exception:
            exc.__cause__ = ssl.SSLError("hostname mismatch")
        raise exc


class RetryLabTransport(httpx.BaseTransport):
    """
    Synchronous HTTPX transport interceptor.
    Injects deterministic faults into requests matching the configured FaultScenario.
    """

    def __init__(
        self,
        scenario: FaultScenario,
        passthrough_transport: httpx.BaseTransport | None = None,
        fallback_response: httpx.Response | None = None,
    ) -> None:
        self.scenario = scenario
        self.passthrough_transport = passthrough_transport
        self.fallback_response = fallback_response

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        method_str = request.method
        headers_dict = dict(request.headers)
        body_bytes = request.read()

        should_fault = self.scenario.should_inject_fault(url_str, method_str)
        self.scenario.record_attempt(
            url=url_str,
            method=method_str,
            headers=headers_dict,
            body=body_bytes,
            injected=should_fault,
        )

        if should_fault:
            # Apply configured latency or dynamic latency profile
            delay = self.scenario.get_delay()
            if delay > 0:
                time.sleep(delay)

            _inject_transport_fault(self.scenario, request, url_str)
            return _build_synthetic_response(request, self.scenario)

        # Passthrough or recovered request
        if self.passthrough_transport is not None:
            return self.passthrough_transport.handle_request(request)

        if self.fallback_response is not None:
            return self.fallback_response

        # Recovered response for offline testing
        status_code = self.scenario.status_code or 200
        headers = {
            "Content-Type": "application/json",
            "X-RetryLab-Status": "recovered",
            **self.scenario.custom_headers,
        }
        if self.scenario.custom_body is not None:
            content = self.scenario.custom_body.encode("utf-8")
        else:
            content = json.dumps({"status": "recovered", "url": url_str}).encode("utf-8")

        return httpx.Response(
            status_code=status_code,
            headers=headers,
            content=content,
            request=request,
        )


class AsyncRetryLabTransport(httpx.AsyncBaseTransport):
    """
    Asynchronous HTTPX transport interceptor for AsyncClient.
    Injects deterministic faults into requests matching the configured FaultScenario.
    """

    def __init__(
        self,
        scenario: FaultScenario,
        passthrough_transport: httpx.AsyncBaseTransport | None = None,
        fallback_response: httpx.Response | None = None,
    ) -> None:
        self.scenario = scenario
        self.passthrough_transport = passthrough_transport
        self.fallback_response = fallback_response

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        method_str = request.method
        headers_dict = dict(request.headers)
        try:
            body_bytes = request.read()
        except Exception:
            body_bytes = b""

        should_fault = self.scenario.should_inject_fault(url_str, method_str)
        self.scenario.record_attempt(
            url=url_str,
            method=method_str,
            headers=headers_dict,
            body=body_bytes,
            injected=should_fault,
        )

        if should_fault:
            delay = self.scenario.get_delay()
            if delay > 0:
                await asyncio.sleep(delay)

            _inject_transport_fault(self.scenario, request, url_str)
            return _build_synthetic_response(request, self.scenario)

        if self.passthrough_transport is not None:
            return await self.passthrough_transport.handle_async_request(request)

        if self.fallback_response is not None:
            return self.fallback_response

        status_code = self.scenario.status_code or 200
        headers = {
            "Content-Type": "application/json",
            "X-RetryLab-Status": "recovered",
            **self.scenario.custom_headers,
        }
        if self.scenario.custom_body is not None:
            content = self.scenario.custom_body.encode("utf-8")
        else:
            content = json.dumps({"status": "recovered", "url": url_str}).encode("utf-8")

        return httpx.Response(
            status_code=status_code,
            headers=headers,
            content=content,
            request=request,
        )
