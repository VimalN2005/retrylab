"""
RetryLab Socket-Level Transport Adapters for HTTPX and Requests.
Translates low-level TCP/socket faults into client-native network exceptions:
- ConnectionResetError -> httpx.RemoteProtocolError / requests.exceptions.ConnectionError
- Blackhole Drop -> httpx.ReadTimeout / requests.exceptions.ReadTimeout
- Premature Socket Close -> httpx.RemoteProtocolError / requests.exceptions.ChunkedEncodingError
- Slow Drip -> trickle stream chunks with artificial latency
"""

from __future__ import annotations

import json
from typing import Any, Iterable, Iterator
import httpx
import requests
from requests.adapters import BaseAdapter
from urllib3.response import HTTPResponse
import io

from retrylab.socket.chaos import SocketChaosConfig, SocketFaultSimulator, SocketFaultType


class SocketByteStream(httpx.SyncByteStream):
    """SyncByteStream wrapper for dripping socket chaos bytes."""

    def __init__(self, chunk_generator: Iterable[bytes]) -> None:
        self._gen = chunk_generator

    def __iter__(self) -> Iterator[bytes]:
        for chunk in self._gen:
            yield chunk

    def close(self) -> None:
        pass


class SocketChaosTransport(httpx.BaseTransport):
    """
    HTTPX Transport that translates socket-level chaos into native HTTPX exceptions and streams.
    """

    def __init__(
        self,
        config: SocketChaosConfig,
        url_pattern: str | None = None,
        default_status_code: int = 200,
        default_body: dict[str, Any] | None = None,
    ) -> None:
        self.config = config
        self.simulator = SocketFaultSimulator(config)
        self.url_pattern = url_pattern
        self.default_status_code = default_status_code
        self.default_body = default_body or {"status": "ok"}
        self._attempt = 0

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if self.url_pattern and self.url_pattern not in url_str:
            return httpx.Response(status_code=404, json={"error": "Not matched by SocketChaosTransport"})

        self._attempt += 1

        if self.simulator.should_trigger(self._attempt):
            fault = self.config.fault_type

            if fault == SocketFaultType.CONNECTION_RESET:
                self.simulator.faults_triggered += 1
                self.simulator.last_fault_applied = fault
                raise httpx.RemoteProtocolError(
                    "Connection reset by peer (Simulated TCP RST)",
                    request=request,
                )

            elif fault == SocketFaultType.SILENT_DROP:
                self.simulator.faults_triggered += 1
                self.simulator.last_fault_applied = fault
                import time
                if self.config.drop_timeout_seconds > 0:
                    time.sleep(self.config.drop_timeout_seconds)
                raise httpx.ReadTimeout(
                    f"Read timed out after {self.config.drop_timeout_seconds}s (Simulated TCP blackhole drop)",
                    request=request,
                )

            elif fault == SocketFaultType.PREMATURE_CLOSE:
                self.simulator.faults_triggered += 1
                self.simulator.last_fault_applied = fault
                raise httpx.RemoteProtocolError(
                    "Connection closed prematurely by peer (Simulated premature FIN)",
                    request=request,
                )

            elif fault == SocketFaultType.MALFORMED_RAW_RESPONSE:
                self.simulator.faults_triggered += 1
                self.simulator.last_fault_applied = fault
                # Return malformed raw bytes
                return httpx.Response(
                    status_code=200,
                    content=self.config.raw_malformed_bytes,
                    headers={"Content-Type": "text/plain"},
                    request=request,
                )

            elif fault == SocketFaultType.SLOW_DRIP:
                body_bytes = json.dumps(self.default_body).encode("utf-8")
                stream_gen = self.simulator.execute_stream(body_bytes, attempt=self._attempt)
                return httpx.Response(
                    status_code=self.default_status_code,
                    headers={"Content-Type": "application/json"},
                    stream=SocketByteStream(stream_gen),
                    request=request,
                )

        # Non-fault path
        return httpx.Response(
            status_code=self.default_status_code,
            headers={"Content-Type": "application/json"},
            json=self.default_body,
            request=request,
        )


class SocketChaosAdapter(BaseAdapter):
    """
    Requests Adapter that translates socket-level chaos into native requests.exceptions.
    """

    def __init__(
        self,
        config: SocketChaosConfig,
        default_status_code: int = 200,
        default_body: dict[str, Any] | None = None,
    ) -> None:
        super().__init__()
        self.config = config
        self.simulator = SocketFaultSimulator(config)
        self.default_status_code = default_status_code
        self.default_body = default_body or {"status": "ok"}
        self._attempt = 0

    def send(
        self,
        request: requests.PreparedRequest,
        stream: bool = False,
        timeout: Any = None,
        verify: Any = True,
        cert: Any = None,
        proxies: Any = None,
    ) -> requests.Response:
        self._attempt += 1

        if self.simulator.should_trigger(self._attempt):
            fault = self.config.fault_type

            if fault == SocketFaultType.CONNECTION_RESET:
                self.simulator.faults_triggered += 1
                self.simulator.last_fault_applied = fault
                raise requests.exceptions.ConnectionError("Connection reset by peer (Simulated TCP RST)")

            elif fault == SocketFaultType.SILENT_DROP:
                self.simulator.faults_triggered += 1
                self.simulator.last_fault_applied = fault
                import time
                if self.config.drop_timeout_seconds > 0:
                    time.sleep(self.config.drop_timeout_seconds)
                raise requests.exceptions.ReadTimeout(
                    f"Read timed out after {self.config.drop_timeout_seconds}s (Simulated TCP blackhole drop)"
                )

            elif fault == SocketFaultType.PREMATURE_CLOSE:
                self.simulator.faults_triggered += 1
                self.simulator.last_fault_applied = fault
                raise requests.exceptions.ChunkedEncodingError("Connection broken: premature socket close")

            elif fault == SocketFaultType.MALFORMED_RAW_RESPONSE:
                self.simulator.faults_triggered += 1
                self.simulator.last_fault_applied = fault
                resp = self.build_response(request, 200, self.config.raw_malformed_bytes)
                return resp

        # Normal response
        body_bytes = json.dumps(self.default_body).encode("utf-8")
        return self.build_response(request, self.default_status_code, body_bytes)

    def build_response(
        self,
        request: requests.PreparedRequest,
        status_code: int,
        content: bytes,
    ) -> requests.Response:
        resp = requests.Response()
        resp.status_code = status_code
        resp.url = request.url or ""
        resp.request = request
        resp.headers = requests.structures.CaseInsensitiveDict({"Content-Type": "application/json"})
        resp.raw = HTTPResponse(
            body=io.BytesIO(content),
            status=status_code,
            headers={"Content-Type": "application/json"},
            preload_content=False,
        )
        return resp

    def close(self) -> None:
        pass
