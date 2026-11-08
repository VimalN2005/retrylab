"""
RetryLab Requests Adapter for legacy and standard SDK interception.
"""

from __future__ import annotations

import io
import json
import time
from typing import Any
import requests
from requests.adapters import BaseAdapter, HTTPAdapter
from requests.structures import CaseInsensitiveDict

from retrylab.models import FaultScenario, FaultType


def _build_synthetic_requests_response(
    request: requests.PreparedRequest,
    scenario: FaultScenario,
) -> requests.Response:
    """Build a synthetic requests.Response object for fault injection."""
    status_code: int = scenario.status_code or 500
    default_headers: dict[str, str] = {
        "Content-Type": "application/json",
        "X-Simulated-By": "RetryLab",
    }
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

    merged_headers = {**default_headers, **scenario.custom_headers}
    content: bytes
    if scenario.custom_body is not None:
        content = scenario.custom_body.encode("utf-8")
    else:
        content = json.dumps(default_body).encode("utf-8")

    response = requests.Response()
    response.status_code = status_code
    response.headers = CaseInsensitiveDict(merged_headers)
    response._content = content
    response.raw = io.BytesIO(content)
    response.url = request.url or ""
    response.request = request
    return response


def _inject_requests_fault(scenario: FaultScenario, request: requests.PreparedRequest, url_str: str) -> None:
    """Raise simulated network, timeout, DNS, or TLS faults for Requests."""
    fault = scenario.fault
    if fault == FaultType.TIMEOUT:
        raise requests.exceptions.ReadTimeout(
            f"Simulated ReadTimeout for {url_str} by RetryLab",
            request=request,
        )

    if fault == FaultType.CONNECTION_RESET:
        raise requests.exceptions.ConnectionError(
            f"Simulated Connection Error for {url_str} by RetryLab",
            request=request,
        )

    if fault == FaultType.DNS_FAILURE:
        import socket
        exc = requests.exceptions.ConnectionError(
            f"Simulated DNS resolution failure (NXDOMAIN) for {url_str} by RetryLab",
            request=request,
        )
        exc.__cause__ = socket.gaierror(-2, "Name or service not known")
        raise exc

    if fault == FaultType.DNS_TIMEOUT:
        raise requests.exceptions.ConnectTimeout(
            f"Simulated DNS resolution timeout for {url_str} by RetryLab",
            request=request,
        )

    if fault == FaultType.TLS_HANDSHAKE_TIMEOUT:
        raise requests.exceptions.ConnectTimeout(
            f"Simulated TLS handshake timeout for {url_str} by RetryLab",
            request=request,
        )

    if fault == FaultType.SSL_CERT_VERIFICATION_FAILED:
        import ssl
        exc = requests.exceptions.SSLError(
            f"[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed for {url_str} by RetryLab",
            request=request,
        )
        try:
            exc.__cause__ = ssl.SSLCertVerificationError(1, "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: certificate has expired")
        except Exception:
            exc.__cause__ = ssl.SSLError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed")
        raise exc

    if fault == FaultType.SSL_HOSTNAME_MISMATCH:
        import ssl
        exc = requests.exceptions.SSLError(
            f"[SSL: CERTIFICATE_VERIFY_FAILED] Hostname mismatch for {url_str} by RetryLab",
            request=request,
        )
        try:
            exc.__cause__ = ssl.CertificateError("hostname mismatch")
        except Exception:
            exc.__cause__ = ssl.SSLError("hostname mismatch")
        raise exc


class RetryLabAdapter(BaseAdapter):
    """
    Requests Adapter that intercepts outgoing requests from requests.Session.
    Usage:
        session = requests.Session()
        adapter = RetryLabAdapter(scenario=scenario)
        session.mount("https://api.stripe.com", adapter)
    """

    def __init__(
        self,
        scenario: FaultScenario,
        passthrough_adapter: BaseAdapter | None = None,
        fallback_response: requests.Response | None = None,
    ) -> None:
        super().__init__()
        self.scenario = scenario
        self.passthrough_adapter = passthrough_adapter
        self.fallback_response = fallback_response

    def send(
        self,
        request: requests.PreparedRequest,
        stream: bool = False,
        timeout: Any = None,
        verify: Any = True,
        cert: Any = None,
        proxies: Any = None,
    ) -> requests.Response:
        url_str = request.url or ""
        method_str = request.method or "GET"
        headers_dict = dict(request.headers)
        body_bytes = request.body if isinstance(request.body, bytes) else (
            request.body.encode("utf-8") if isinstance(request.body, str) else b""
        )

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
                time.sleep(delay)

            _inject_requests_fault(self.scenario, request, url_str)
            return _build_synthetic_requests_response(request, self.scenario)

        # Non-faulting request (recovered or unmatched)
        if self.passthrough_adapter is not None:
            return self.passthrough_adapter.send(
                request,
                stream=stream,
                timeout=timeout,
                verify=verify,
                cert=cert,
                proxies=proxies,
            )

        if self.fallback_response is not None:
            return self.fallback_response

        # Recovered 200 response
        recovered_resp = requests.Response()
        recovered_resp.status_code = self.scenario.status_code or 200
        headers_dict = {
            "Content-Type": "application/json",
            "X-RetryLab-Status": "recovered",
            **self.scenario.custom_headers,
        }
        recovered_resp.headers = CaseInsensitiveDict(headers_dict)
        if self.scenario.custom_body is not None:
            recovered_content = self.scenario.custom_body.encode("utf-8")
        else:
            recovered_content = json.dumps({"status": "recovered", "url": url_str}).encode("utf-8")

        recovered_resp._content = recovered_content
        recovered_resp.raw = io.BytesIO(recovered_content)
        recovered_resp.url = url_str
        recovered_resp.request = request
        return recovered_resp

    def close(self) -> None:
        if self.passthrough_adapter is not None:
            self.passthrough_adapter.close()
