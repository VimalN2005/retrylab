"""
RetryLab Chaos Studio Web Playground HTTP Server & API Engine.
Provides REST endpoints for preset inspection, scenario execution, telemetry auditing,
and polyglot multi-language code generation.
"""

from __future__ import annotations

import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Optional
import httpx

from retrylab.matrix import PolyglotChaosMatrix, PolyglotScenarioSchema
from retrylab.models import FaultScenario, FaultType
from retrylab.reporting.generator import generate_reliability_report
from retrylab.studio.presets import get_all_presets, get_preset_by_id
from retrylab.transport import RetryLabTransport
from retrylab.tui.scorecard import ScorecardEvaluator


class ChaosStudioHandler(BaseHTTPRequestHandler):
    """HTTP Request Handler for Chaos Studio REST API and Web UI."""

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress default HTTP request logging to keep console clean."""
        return

    def _send_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def _send_json_response(self, data: Any, status: int = 200) -> None:
        body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self) -> None:
        path = self.path.split("?")[0]

        if path == "/api/presets":
            self._send_json_response({"presets": get_all_presets()})
            return

        if path == "/api/health":
            self._send_json_response({"status": "ok", "service": "retrylab-chaos-studio"})
            return

        # Serve Web UI
        if path == "/" or path == "/index.html":
            try:
                from retrylab.studio.assets import render_studio_html
                html_content = render_studio_html()
            except ImportError:
                html_content = "<html><body><h1>RetryLab Chaos Studio</h1></body></html>"

            body = html_content.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(body)
            return

        self.send_error(404, "Endpoint Not Found")

    def do_POST(self) -> None:
        path = self.path.split("?")[0]
        content_length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(content_length) if content_length > 0 else b"{}"

        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except Exception as exc:
            self._send_json_response({"error": f"Invalid JSON payload: {exc}"}, status=400)
            return

        if path == "/api/run":
            self._handle_run_scenario(payload)
            return

        if path == "/api/export":
            self._handle_export_scenario(payload)
            return

        self.send_error(404, "Endpoint Not Found")

    def _handle_run_scenario(self, payload: dict[str, Any]) -> None:
        """Execute scenario in-process and return report, scorecard, and timeline."""
        name = payload.get("name", "custom_chaos_scenario")
        target = payload.get("target", "https://api.stripe.com/v1/charges")
        method = payload.get("method", "POST")
        fault_str = payload.get("fault", "http_status")
        fail_count = int(payload.get("fail_count", 1))
        status_code = int(payload.get("status_code", 503))
        delay_ms = int(payload.get("delay_ms", 50))
        idempotency_header = payload.get("idempotency_header", "Idempotency-Key")

        # Map fault string to FaultType
        if fault_str == "timeout":
            fault_type = FaultType.TIMEOUT
        elif fault_str in ("disconnect", "network_error", "socket_reset"):
            fault_type = FaultType.CONNECTION_RESET
        elif status_code == 429:
            fault_type = FaultType.RATE_LIMIT_429
        elif status_code == 500:
            fault_type = FaultType.SERVER_ERROR_500
        else:
            fault_type = FaultType.SERVER_ERROR_503

        scenario = FaultScenario(
            name=name,
            target=target,
            method=method,
            fault=fault_type,
            fail_count=fail_count,
            delay_seconds=round(delay_ms / 1000.0, 3),
        )

        transport = RetryLabTransport(scenario=scenario)
        target_clean = target.replace("*", "checkout")
        idemp_val = f"studio_idemp_{int(time.time() * 1000)}"
        request_headers = {idempotency_header: idemp_val}
        test_payload = {"service": name, "timestamp": time.time(), "amount": 9900}

        timeline: list[dict[str, Any]] = []
        total_steps = fail_count + 1

        with httpx.Client(transport=transport) as client:
            for step_idx in range(1, total_steps + 1):
                t0 = time.perf_counter()
                injected_err: Optional[str] = None
                resp_status = 200

                try:
                    resp = client.request(
                        method,
                        target_clean,
                        json=test_payload,
                        headers=request_headers,
                        timeout=5.0,
                    )
                    resp_status = resp.status_code
                except httpx.HTTPError as exc:
                    injected_err = type(exc).__name__
                    resp_status = 0

                elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
                timeline.append({
                    "attempt": step_idx,
                    "method": method,
                    "target": target_clean,
                    "status_code": resp_status,
                    "error": injected_err,
                    "was_fault_injected": (injected_err is not None or resp_status >= 400),
                    "latency_ms": elapsed_ms,
                    "idempotency_key": idemp_val,
                })

        report = generate_reliability_report(scenario=scenario, idempotency_header=idempotency_header)
        scorecard = ScorecardEvaluator.evaluate_reports([report])

        self._send_json_response({
            "status": "success",
            "scenario": {
                "name": name,
                "target": target,
                "method": method,
                "fault": fault_str,
                "fail_count": fail_count,
            },
            "timeline": timeline,
            "report": report.model_dump(),
            "scorecard": scorecard.to_dict(),
        })

    def _handle_export_scenario(self, payload: dict[str, Any]) -> None:
        """Compile scenario payload into native Python, Go, TypeScript, and YAML code snippets."""
        name = payload.get("name", "chaos_scenario")
        target = payload.get("target", "https://api.stripe.com/v1/charges")
        method = payload.get("method", "POST")
        fault = payload.get("fault", "http_status")
        fail_count = int(payload.get("fail_count", 1))
        status_code = int(payload.get("status_code", 503))
        delay_ms = int(payload.get("delay_ms", 50))

        schema = PolyglotScenarioSchema(
            name=name,
            url_pattern=target,
            method=method,
            fault=fault,
            fail_count=fail_count,
            status_code=status_code,
            delay_ms=delay_ms,
        )

        self._send_json_response({
            "yaml": PolyglotChaosMatrix.to_yaml_snippet(schema),
            "python": PolyglotChaosMatrix.to_python_snippet(schema),
            "go": PolyglotChaosMatrix.to_go_snippet(schema),
            "typescript": PolyglotChaosMatrix.to_ts_snippet(schema),
        })


class ChaosStudioServer(HTTPServer):
    """HTTP Server for Chaos Studio with socket address reuse."""

    allow_reuse_address = True


def create_studio_server(host: str = "127.0.0.1", port: int = 8400) -> ChaosStudioServer:
    """Instantiate a new Chaos Studio server."""
    return ChaosStudioServer((host, port), ChaosStudioHandler)


def start_background_studio(
    host: str = "127.0.0.1",
    port: int = 8400,
) -> tuple[ChaosStudioServer, threading.Thread]:
    """Start Chaos Studio server in a background daemon thread."""
    server = create_studio_server(host=host, port=port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread
