"""
RetryLab Chaos Sidecar: Zero-Code Containerized Interception Proxy.
Enables attaching RetryLab fault injection, rate-limiting, and resilience verification
to any microservice, Kubernetes pod, or Docker Compose stack (Python, Go, Node, Java, Rust, Ruby).
"""

from __future__ import annotations

import json
import socket
import sys
import threading
import time
from dataclasses import asdict, dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from retrylab import __version__
from retrylab.models import FaultScenario, FaultType
from retrylab.scenarios import ScenarioStep, SequentialScenario, StepKind, load_scenario_from_yaml

ScenarioInstance = Union[FaultScenario, SequentialScenario]


@dataclass
class SidecarMetrics:
    start_time: float = field(default_factory=time.time)
    total_intercepted: int = 0
    faults_injected: int = 0
    passthroughs: int = 0
    requests_by_status: Dict[int, int] = field(default_factory=dict)
    requests_by_method: Dict[str, int] = field(default_factory=dict)
    recent_latencies_ms: List[float] = field(default_factory=list)

    @property
    def uptime_seconds(self) -> float:
        return round(time.time() - self.start_time, 2)

    def record_request(self, method: str, status_code: int, latency_ms: float, was_fault: bool) -> None:
        self.total_intercepted += 1
        if was_fault:
            self.faults_injected += 1
        else:
            self.passthroughs += 1

        self.requests_by_status[status_code] = self.requests_by_status.get(status_code, 0) + 1
        self.requests_by_method[method] = self.requests_by_method.get(method, 0) + 1

        self.recent_latencies_ms.append(round(latency_ms, 2))
        if len(self.recent_latencies_ms) > 100:
            self.recent_latencies_ms.pop(0)

    def to_dict(self) -> Dict[str, Any]:
        avg_lat = (
            round(sum(self.recent_latencies_ms) / len(self.recent_latencies_ms), 2)
            if self.recent_latencies_ms
            else 0.0
        )
        return {
            "uptime_seconds": self.uptime_seconds,
            "total_intercepted": self.total_intercepted,
            "faults_injected": self.faults_injected,
            "passthroughs": self.passthroughs,
            "requests_by_status": self.requests_by_status,
            "requests_by_method": self.requests_by_method,
            "average_latency_ms": avg_lat,
        }


@dataclass
class SidecarConfig:
    host: str = "0.0.0.0"
    port: int = 8080
    target_upstream: Optional[str] = None  # If set, acts as reverse proxy forwarding to upstream
    scenario: Optional[ScenarioInstance] = None
    scenario_path: Optional[str] = None
    metrics_enabled: bool = True
    cors_enabled: bool = True
    timeout_seconds: float = 15.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "host": self.host,
            "port": self.port,
            "target_upstream": self.target_upstream,
            "scenario_name": self.scenario.name if self.scenario else None,
            "scenario_path": self.scenario_path,
            "metrics_enabled": self.metrics_enabled,
            "cors_enabled": self.cors_enabled,
            "timeout_seconds": self.timeout_seconds,
        }


class SidecarProxyHandler(BaseHTTPRequestHandler):
    """
    HTTP Request Handler routing requests through RetryLab scenarios or forwarding to upstream.
    """

    config: SidecarConfig
    metrics: SidecarMetrics
    scenario: Optional[ScenarioInstance] = None

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress standard BaseHTTPRequestHandler stderr logging for clean console/tests."""
        return

    def _send_cors_headers(self) -> None:
        if self.config.cors_enabled:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, PATCH, OPTIONS, HEAD")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, Idempotency-Key, X-Request-ID")

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._send_cors_headers()
        self.end_headers()

    def do_HEAD(self) -> None:
        self._handle_request("HEAD")

    def do_GET(self) -> None:
        self._handle_request("GET")

    def do_POST(self) -> None:
        self._handle_request("POST")

    def do_PUT(self) -> None:
        self._handle_request("PUT")

    def do_DELETE(self) -> None:
        self._handle_request("DELETE")

    def do_PATCH(self) -> None:
        self._handle_request("PATCH")

    def _resolve_target_url(self) -> str:
        """Determine downstream target URL in reverse-proxy or forward-proxy mode."""
        if self.config.target_upstream:
            base = self.config.target_upstream.rstrip("/")
            path = self.path
            return f"{base}{path}"

        if self.path.startswith("http://") or self.path.startswith("https://"):
            return self.path

        host = self.headers.get("Host", "localhost")
        scheme = "https" if "443" in host else "http"
        return f"{scheme}://{host}{self.path}"

    def _handle_request(self, method: str) -> None:
        t0 = time.perf_counter()

        # 1. Admin & Diagnostic Endpoints
        if self.path == "/_retrylab/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self._send_cors_headers()
            self.end_headers()
            resp = {
                "status": "UP",
                "sidecar": "healthy",
                "version": __version__,
                "uptime_seconds": self.metrics.uptime_seconds,
                "scenario": self.scenario.name if self.scenario else None,
            }
            self.wfile.write(json.dumps(resp, indent=2).encode("utf-8"))
            return

        if self.path == "/_retrylab/metrics":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self._send_cors_headers()
            self.end_headers()
            resp = {
                "version": __version__,
                "config": self.config.to_dict(),
                "metrics": self.metrics.to_dict(),
            }
            self.wfile.write(json.dumps(resp, indent=2).encode("utf-8"))
            return

        if self.path == "/_retrylab/scenario":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self._send_cors_headers()
            self.end_headers()
            if self.scenario:
                resp = {
                    "scenario": self.scenario.name,
                    "total_attempts": getattr(self.scenario, "_attempts", 0),
                    "target": getattr(self.scenario, "target", "*"),
                }
            else:
                resp = {"scenario": None, "message": "No active scenario loaded (pure pass-through)"}
            self.wfile.write(json.dumps(resp, indent=2).encode("utf-8"))
            return

        if self.path == "/_retrylab/reset" and method == "POST":
            if self.scenario and hasattr(self.scenario, "reset"):
                self.scenario.reset()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps({"status": "reset", "scenario": self.scenario.name if self.scenario else None}).encode("utf-8"))
            return

        target_url = self._resolve_target_url()

        # Read request body if present
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else b""
        headers_dict = dict(self.headers)

        # 2. Match against active Chaos Scenario
        if self.scenario and self.scenario.matches(target_url, method):
            should_fault = False
            status_to_inject = 500
            resp_body = b'{"error": "Injected chaos fault"}'
            resp_headers: Dict[str, str] = {}
            delay_sec = 0.0

            if isinstance(self.scenario, SequentialScenario):
                step = self.scenario.get_current_step()
                should_fault = (step.kind == StepKind.FAULT)
                if should_fault:
                    status_to_inject = step.status_code or 500
                    resp_body = step.custom_body.encode("utf-8") if step.custom_body else b'{"error": "Sequential fault"}'
                    resp_headers = step.custom_headers or {}
                    delay_sec = (step.latency_ms or 0.0) / 1000.0
                self.scenario.record_attempt(target_url, method, headers_dict, body, should_fault)
            elif isinstance(self.scenario, FaultScenario):
                should_fault = self.scenario.should_inject_fault(target_url, method)
                if should_fault:
                    fault_code_map = {
                        FaultType.RATE_LIMIT_429: 429,
                        FaultType.SERVICE_UNAVAILABLE_503: 503,
                        FaultType.BAD_GATEWAY_502: 502,
                        FaultType.GATEWAY_TIMEOUT_504: 504,
                        FaultType.TIMEOUT: 504,
                        FaultType.SERVER_ERROR_500: 500,
                    }
                    status_to_inject = self.scenario.status_code or fault_code_map.get(self.scenario.fault, 500)
                    resp_body = self.scenario.custom_body.encode("utf-8") if self.scenario.custom_body else json.dumps({"error": f"Simulated {self.scenario.fault.value}"}).encode("utf-8")
                    resp_headers = dict(self.scenario.custom_headers)
                    delay_sec = self.scenario.delay_seconds or (self.scenario.latency_profile.sample() / 1000.0 if self.scenario.latency_profile else 0.0)
                self.scenario.record_attempt(target_url, method, headers_dict, body, should_fault)

            if should_fault:
                if delay_sec > 0:
                    time.sleep(delay_sec)

                self.send_response(status_to_inject)
                self.send_header("Content-Type", resp_headers.get("Content-Type", "application/json"))
                self.send_header("X-RetryLab-Injected", "true")
                self.send_header("X-RetryLab-Scenario", self.scenario.name)
                for hk, hv in resp_headers.items():
                    if hk.lower() != "content-type":
                        self.send_header(hk, hv)
                self._send_cors_headers()
                self.end_headers()

                if method != "HEAD":
                    self.wfile.write(resp_body)

                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                self.metrics.record_request(method, status_to_inject, elapsed_ms, was_fault=True)
                return

        # 3. Pass-through mode: Forward to upstream if target_upstream configured
        if self.config.target_upstream:
            try:
                req_headers = {k: v for k, v in self.headers.items() if k.lower() not in ["host", "content-length"]}
                req = Request(target_url, data=body if body else None, headers=req_headers, method=method)
                with urlopen(req, timeout=self.config.timeout_seconds) as upstream_resp:
                    code = upstream_resp.getcode()
                    resp_data = upstream_resp.read()
                    self.send_response(code)
                    for hk, hv in upstream_resp.headers.items():
                        if hk.lower() not in ["transfer-encoding", "content-length"]:
                            self.send_header(hk, hv)
                    self._send_cors_headers()
                    self.end_headers()
                    if method != "HEAD":
                        self.wfile.write(resp_data)
                    elapsed_ms = (time.perf_counter() - t0) * 1000.0
                    self.metrics.record_request(method, code, elapsed_ms, was_fault=False)
                    return
            except HTTPError as exc:
                err_data = exc.read()
                self.send_response(exc.code)
                for hk, hv in exc.headers.items():
                    if hk.lower() not in ["transfer-encoding", "content-length"]:
                        self.send_header(hk, hv)
                self._send_cors_headers()
                self.end_headers()
                if method != "HEAD":
                    self.wfile.write(err_data)
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                self.metrics.record_request(method, exc.code, elapsed_ms, was_fault=False)
                return
            except Exception as exc:
                err_msg = json.dumps({"error": f"Upstream connection failed: {exc}"}).encode("utf-8")
                self.send_response(502)
                self.send_header("Content-Type", "application/json")
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(err_msg)
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                self.metrics.record_request(method, 502, elapsed_ms, was_fault=False)
                return

        # 4. Default Mock Response if no upstream configured and scenario passed
        success_msg = json.dumps({
            "message": "RetryLab Sidecar Pass-Through Success",
            "method": method,
            "url": target_url,
            "status": 200,
        }).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("X-RetryLab-Passthrough", "true")
        self._send_cors_headers()
        self.end_headers()
        if method != "HEAD":
            self.wfile.write(success_msg)

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        self.metrics.record_request(method, 200, elapsed_ms, was_fault=False)


class RetryLabSidecar:
    """Multi-threaded containerized chaos sidecar proxy server."""

    def __init__(self, config: Optional[SidecarConfig] = None):
        self.config = config or SidecarConfig()
        self.metrics = SidecarMetrics()

        # Load scenario from path if specified
        if self.config.scenario_path and not self.config.scenario:
            p = Path(self.config.scenario_path)
            if p.exists():
                self.config.scenario = load_scenario_from_yaml(p)

        self._server: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    @property
    def server_port(self) -> int:
        if self._server:
            return self._server.server_address[1]
        return self.config.port

    @property
    def server_url(self) -> str:
        return f"http://{self.config.host}:{self.server_port}"

    def create_server(self) -> ThreadingHTTPServer:
        handler_cls = type(
            "ConfiguredSidecarHandler",
            (SidecarProxyHandler,),
            {
                "config": self.config,
                "metrics": self.metrics,
                "scenario": self.config.scenario,
            },
        )
        server = ThreadingHTTPServer((self.config.host, self.config.port), handler_cls)
        # Avoid "Address already in use" on rapid restarts
        server.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server = server
        self.config.port = server.server_address[1]
        return server

    def start(self) -> None:
        """Start server synchronously (blocks calling thread)."""
        server = self.create_server()
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            self.stop()

    def start_background(self) -> threading.Thread:
        """Start server in background daemon thread (non-blocking for tests/SDKs)."""
        server = self.create_server()
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        self._thread = t
        time.sleep(0.08)  # Allow socket to bind
        return t

    def stop(self) -> None:
        """Gracefully shut down sidecar proxy."""
        if self._server:
            if self._thread and self._thread.is_alive():
                self._server.shutdown()
            self._server.server_close()
            self._server = None
            self._thread = None


def start_background_sidecar(config: Optional[SidecarConfig] = None) -> Tuple[RetryLabSidecar, threading.Thread]:
    """Helper to instantiate and launch background sidecar proxy."""
    sidecar = RetryLabSidecar(config=config)
    t = sidecar.start_background()
    return sidecar, t
