"""
RetryLab Streaming Response Interceptor & Server-Sent Events (SSE) Protocol Engine.
Enables transport-level interception and manipulation of streaming HTTP responses
(OpenAI/Anthropic chunk streams, SSE event streams, raw byte streams).
"""

from __future__ import annotations

import json
from typing import Any, Callable, Generator, Iterable, Iterator
import httpx
from pydantic import BaseModel, Field


class SSEEvent(BaseModel):
    """Represents a discrete Server-Sent Event (W3C standard)."""

    data: str = ""
    event: str | None = None
    id: str | None = None
    retry: int | None = None

    def encode(self) -> bytes:
        """Encodes the SSE event into wire-format bytes ending in double newline."""
        lines: list[str] = []
        if self.event:
            lines.append(f"event: {self.event}")
        if self.id:
            lines.append(f"id: {self.id}")
        if self.retry is not None:
            lines.append(f"retry: {self.retry}")

        for part in self.data.split("\n"):
            lines.append(f"data: {part}")

        return ("\n".join(lines) + "\n\n").encode("utf-8")

    @classmethod
    def from_json(cls, data: dict[str, Any], event: str | None = None, event_id: str | None = None) -> SSEEvent:
        """Convenience factory to produce an SSEEvent with a JSON-serialized payload."""
        return cls(data=json.dumps(data, separators=(",", ":")), event=event, id=event_id)


class SSEStreamParser:
    """
    Incremental parser for Server-Sent Events (SSE) data streams.
    Decodes arbitrary byte chunks into parsed SSEEvent instances.
    """

    def __init__(self) -> None:
        self._buffer: str = ""

    def feed(self, chunk: bytes | str) -> list[SSEEvent]:
        """
        Feeds a chunk of bytes or text into the parser, returning any fully-formed
        SSE events assembled by the chunk.
        """
        if isinstance(chunk, bytes):
            text = chunk.decode("utf-8", errors="replace")
        else:
            text = chunk

        self._buffer += text
        events: list[SSEEvent] = []

        # Split on standard double newline SSE message boundaries
        while "\n\n" in self._buffer:
            raw_event, self._buffer = self._buffer.split("\n\n", 1)
            parsed = self._parse_event_block(raw_event)
            if parsed is not None:
                events.append(parsed)

        return events

    def _parse_event_block(self, block: str) -> SSEEvent | None:
        lines = block.splitlines()
        data_parts: list[str] = []
        event_name: str | None = None
        event_id: str | None = None
        retry_val: int | None = None

        for line in lines:
            line = line.strip()
            if not line or line.startswith(":"):  # Comment / ping line
                continue

            if ":" in line:
                field, value = line.split(":", 1)
                value = value.lstrip(" ")
            else:
                field, value = line, ""

            if field == "data":
                data_parts.append(value)
            elif field == "event":
                event_name = value
            elif field == "id":
                event_id = value
            elif field == "retry":
                try:
                    retry_val = int(value)
                except ValueError:
                    pass

        if not data_parts and not event_name and not event_id:
            return None

        return SSEEvent(
            data="\n".join(data_parts),
            event=event_name,
            id=event_id,
            retry=retry_val,
        )


class StreamingByteIterator(httpx.SyncByteStream):
    """
    Synchronous byte iterator implementing httpx.SyncByteStream for streaming responses.
    """

    def __init__(self, chunk_generator: Iterable[bytes | str]) -> None:
        self._gen = chunk_generator

    def __iter__(self) -> Iterator[bytes]:
        for chunk in self._gen:
            if isinstance(chunk, str):
                yield chunk.encode("utf-8")
            else:
                yield chunk

    def close(self) -> None:
        """Closes any underlying generator if possible."""
        if hasattr(self._gen, "close"):
            self._gen.close()


class StreamingFaultTransport(httpx.BaseTransport):
    """
    HTTPX Transport that matches requests and yields configurable streaming responses.
    """

    def __init__(
        self,
        stream_factory: Callable[[httpx.Request], Iterable[bytes | str]],
        url_pattern: str | None = None,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.stream_factory = stream_factory
        self.url_pattern = url_pattern
        self.status_code = status_code
        self.headers = headers or {"content-type": "text/event-stream", "cache-control": "no-cache"}

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if self.url_pattern and self.url_pattern not in url_str:
            return httpx.Response(status_code=404, json={"error": "Not matched by StreamingFaultTransport"})

        chunk_iter = self.stream_factory(request)
        stream = StreamingByteIterator(chunk_iter)

        return httpx.Response(
            status_code=self.status_code,
            headers=self.headers,
            stream=stream,
            request=request,
        )
