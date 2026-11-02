"""
RetryLab Lightweight HTTP Proxy Daemon for Cross-Language Resilience Testing.
Allows testing Go, Node.js, Ruby, and curl microservices against RetryLab scenarios.
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Union
from urllib.parse import urlparse

from retrylab.models import FaultScenario, FaultType
from retrylab.scenarios.sequential import SequentialScenario

ScenarioInstance = Union[FaultScenario, SequentialScenario]


class RetryLabProxyHandler(BaseHTTPRequestHandler):
    """
    HTTP Request Handler that routes requests through a RetryLab resilience scenario.
    """

    scenario: ScenarioInstance

    def _resolve_target_url(self) -> str:
        """Constructs target URL from Host header and path, or raw path if full URL."""
        if self.path.startswith("http://") or self.path.startswith("https://"):
            return self.path
        host = self.headers.get("Host", "localhost")
        scheme = "https" if "443" in host else "http"
        return f"{scheme}://{host}{self.path}"

    def do_GET(self) -> None:
        self._handle_any_request("GET")

    def do_POST(self) -> None:
        self._handle_any_request("POST")

    def do_PUT(self) -> None:
        self._handle_any_request("PUT")

    def do_DELETE(self) -> None:
        self._handle_any_request("DELETE")

    def do_PATCH(self) -> None:
        self._handle_any_request("PATCH")

    def _handle_any_request(self, method: str) -> None:
        # 1. Admin endpoints
        if self.path == "/_retrylab/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "scenario": self.scenario.name}).encode())
            return

        if self.path == "/_retrylab/report":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            report_data = {
                "scenario": self.scenario.name,
                "total_attempts": self.scenario.total_attempts,
                "records": [r.to_safe_dict() for r in self.scenario.recorded_requests],
            }
            self.wfile.write(json.dumps(report_data).encode())
            return

        # 2. Extract request metadata
        target_url = self._resolve_target_url()
        content_length = int(self.headers.get("Content-Length", 0))
        body_bytes = self.rfile.read(content_length) if content_length > 0 else b""
        headers_dict = {k: v for k, v in self.headers.items()}

        should_fault = self.scenario.should_inject_fault(target_url, method)
        self.scenario.record_attempt(
            url=target_url,
            method=method,
            headers=headers_dict,
            body=body_bytes,
            injected=should_fault,
        )

        if should_fault:
            delay = self.scenario.get_delay()
            if delay > 0:
                time.sleep(delay)

            if self.scenario.fault == FaultType.TIMEOUT:
                # Simulate timeout by returning 504 Gateway Timeout
                self.send_response(504)
                self.send_header("Content-Type", "application/json")
                self.send_header("X-Simulated-By", "RetryLab-Proxy")
                self.end_headers()
                self.wfile.write(b'{"error": "Simulated Gateway Timeout by RetryLab"}')
                return

            if self.scenario.fault == FaultType.CONNECTION_RESET:
                # Abruptly terminate connection
                self.close_connection = True
                return

            # Status code fault (429, 500, 503, etc.)
            status = self.scenario.status_code or (
                429 if self.scenario.fault == FaultType.RATE_LIMIT_429 else 500
            )
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("X-Simulated-By", "RetryLab-Proxy")
            if self.scenario.fault in (FaultType.RATE_LIMIT_429, FaultType.SERVICE_UNAVAILABLE_503):
                self.send_header("Retry-After", str(self.scenario.retry_after_seconds))

            for k, v in self.scenario.custom_headers.items():
                self.send_header(k, v)
            self.end_headers()

            body_content = (
                self.scenario.custom_body.encode("utf-8")
                if self.scenario.custom_body is not None
                else json.dumps({"error": f"Simulated {self.scenario.fault.value}"}).encode()
            )
            self.wfile.write(body_content)
            return

        # Recovered / Non-faulting response
        status = self.scenario.status_code or 200
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("X-RetryLab-Status", "recovered")
        for k, v in self.scenario.custom_headers.items():
            self.send_header(k, v)
        self.end_headers()

        content = (
            self.scenario.custom_body.encode("utf-8")
            if self.scenario.custom_body is not None
            else json.dumps({"status": "recovered", "url": target_url}).encode()
        )
        self.wfile.write(content)

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress default HTTP stderr logging during tests."""
        return


def create_proxy_server(
    scenario: ScenarioInstance,
    host: str = "127.0.0.1",
    port: int = 8080,
) -> HTTPServer:
    """Creates a configured HTTPServer instance bound to a scenario."""
    handler_class = type(
        "ConfiguredRetryLabProxyHandler",
        (RetryLabProxyHandler,),
        {"scenario": scenario},
    )
    return HTTPServer((host, port), handler_class)


def start_background_proxy(
    scenario: ScenarioInstance,
    host: str = "127.0.0.1",
    port: int = 0,
) -> tuple[HTTPServer, threading.Thread, str]:
    """
    Starts the proxy server in a background daemon thread.
    Returns (server, thread, server_url).
    """
    server = create_proxy_server(scenario, host=host, port=port)
    actual_port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, f"http://{host}:{actual_port}"
