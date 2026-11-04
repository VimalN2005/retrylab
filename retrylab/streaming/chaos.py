"""
RetryLab Mid-Stream Chaos & Fault Injection Engine.
Injects real-world streaming anomalies into Server-Sent Events (SSE) and LLM token streams:
- Premature stream truncation (sudden TCP close / EOF)
- Packet loss & chunk dropouts
- Corrupted JSON / malformed SSE delimiters
- Mid-stream stalls & token latency freezes
- In-band error payloads (429/500 mid-stream generation failure)
"""

from __future__ import annotations

import json
import time
from enum import Enum
from typing import Any, Iterable, Iterator
from pydantic import BaseModel, Field

from retrylab.streaming.interceptor import SSEEvent


class StreamingChaosMode(str, Enum):
    """Supported chaos failure modes for streaming responses."""

    NONE = "none"
    TRUNCATE = "truncate"
    DROP_CHUNKS = "drop_chunks"
    CORRUPT_JSON = "corrupt_json"
    MID_STREAM_STALL = "mid_stream_stall"
    INJECT_ERROR = "inject_error"


class StreamingChaosConfig(BaseModel):
    """Configuration options for streaming chaos injection."""

    mode: StreamingChaosMode = StreamingChaosMode.NONE
    truncate_after_chunks: int = 3
    drop_chunk_indices: list[int] = Field(default_factory=lambda: [2])
    stall_after_chunk: int = 2
    stall_seconds: float = 0.5
    corrupt_chunk_index: int = 2
    corrupt_payload: bytes = b'data: {"choices": [{"delta": {"content": "broken_json_token\n\n'
    injected_error_payload: dict[str, Any] = Field(
        default_factory=lambda: {
            "error": {
                "message": "Engine overloaded mid-generation. Please retry.",
                "type": "server_error",
                "code": 503,
            }
        }
    )


class ChaosStreamGenerator:
    """
    Wraps an iterable or generator of stream chunks and injects configured chaos faults.
    """

    def __init__(
        self,
        source: Iterable[bytes | str | SSEEvent],
        config: StreamingChaosConfig,
    ) -> None:
        self.source = source
        self.config = config
        self.chunks_emitted: int = 0
        self.chunks_dropped: int = 0
        self.fault_injected: str | None = None

    def __iter__(self) -> Iterator[bytes]:
        chunk_idx = 0

        for raw_item in self.source:
            chunk_idx += 1

            # Convert item to bytes
            if isinstance(raw_item, SSEEvent):
                item_bytes = raw_item.encode()
            elif isinstance(raw_item, str):
                item_bytes = raw_item.encode("utf-8")
            else:
                item_bytes = raw_item

            # 1. TRUNCATE MODE
            if self.config.mode == StreamingChaosMode.TRUNCATE:
                if chunk_idx > self.config.truncate_after_chunks:
                    self.fault_injected = f"truncated_after_chunk_{self.config.truncate_after_chunks}"
                    return  # Abruptly terminate stream
                self.chunks_emitted += 1
                yield item_bytes
                continue

            # 2. DROP CHUNKS MODE
            if self.config.mode == StreamingChaosMode.DROP_CHUNKS:
                if chunk_idx in self.config.drop_chunk_indices:
                    self.chunks_dropped += 1
                    self.fault_injected = f"dropped_chunk_{chunk_idx}"
                    continue  # Silently discard chunk
                self.chunks_emitted += 1
                yield item_bytes
                continue

            # 3. CORRUPT JSON MODE
            if self.config.mode == StreamingChaosMode.CORRUPT_JSON:
                if chunk_idx == self.config.corrupt_chunk_index:
                    self.fault_injected = f"corrupted_chunk_{chunk_idx}"
                    self.chunks_emitted += 1
                    yield self.config.corrupt_payload
                    continue
                self.chunks_emitted += 1
                yield item_bytes
                continue

            # 4. MID-STREAM STALL MODE
            if self.config.mode == StreamingChaosMode.MID_STREAM_STALL:
                if chunk_idx == self.config.stall_after_chunk + 1:
                    time.sleep(self.config.stall_seconds)
                    self.fault_injected = f"stalled_{self.config.stall_seconds}s_at_chunk_{chunk_idx}"
                self.chunks_emitted += 1
                yield item_bytes
                continue

            # 5. INJECT ERROR MODE
            if self.config.mode == StreamingChaosMode.INJECT_ERROR:
                if chunk_idx == self.config.corrupt_chunk_index:
                    err_event = SSEEvent.from_json(self.config.injected_error_payload, event="error")
                    self.fault_injected = f"injected_error_at_chunk_{chunk_idx}"
                    self.chunks_emitted += 1
                    yield err_event.encode()
                    return  # Terminate after error
                self.chunks_emitted += 1
                yield item_bytes
                continue

            # Default / None: Pass through untouched
            self.chunks_emitted += 1
            yield item_bytes
