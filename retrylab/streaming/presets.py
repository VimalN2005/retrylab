"""
RetryLab Streaming Format Presets (OpenAI, Anthropic) & Ready-to-Use Fault Transports.
Enables instant drop-in simulation of AI LLM token streams with mid-stream chaos.
"""

from __future__ import annotations

import json
import uuid
from typing import Any
import httpx

from retrylab.streaming.chaos import ChaosStreamGenerator, StreamingChaosConfig, StreamingChaosMode
from retrylab.streaming.interceptor import SSEEvent, StreamingFaultTransport


def build_openai_chat_stream(
    content: str,
    model: str = "gpt-4o",
    words_per_chunk: int = 1,
) -> list[SSEEvent]:
    """
    Constructs a list of standard OpenAI Chat Completion SSE chunks.
    Format: data: {"id":"chatcmpl-...","choices":[{"delta":{"content":"..."}}]}
    """
    chat_id = f"chatcmpl_{uuid.uuid4().hex[:12]}"
    words = content.split(" ")
    events: list[SSEEvent] = []

    # Initial chunk (role: assistant)
    init_chunk = {
        "id": chat_id,
        "object": "chat.completion.chunk",
        "created": 1730000000,
        "model": model,
        "choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": None}],
    }
    events.append(SSEEvent.from_json(init_chunk))

    # Text delta chunks
    i = 0
    while i < len(words):
        chunk_words = words[i : i + words_per_chunk]
        prefix = " " if i > 0 else ""
        text_piece = prefix + " ".join(chunk_words)

        delta_chunk = {
            "id": chat_id,
            "object": "chat.completion.chunk",
            "created": 1730000000,
            "model": model,
            "choices": [{"index": 0, "delta": {"content": text_piece}, "finish_reason": None}],
        }
        events.append(SSEEvent.from_json(delta_chunk))
        i += words_per_chunk

    # Final completion chunk & [DONE]
    final_chunk = {
        "id": chat_id,
        "object": "chat.completion.chunk",
        "created": 1730000000,
        "model": model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
    events.append(SSEEvent.from_json(final_chunk))
    events.append(SSEEvent(data="[DONE]"))

    return events


def build_anthropic_messages_stream(
    content: str,
    model: str = "claude-3-5-sonnet-20241022",
    words_per_chunk: int = 1,
) -> list[SSEEvent]:
    """
    Constructs a list of standard Anthropic Messages API SSE events:
    event: message_start
    event: content_block_start
    event: content_block_delta
    event: content_block_stop
    event: message_stop
    """
    msg_id = f"msg_{uuid.uuid4().hex[:12]}"
    events: list[SSEEvent] = []

    # 1. message_start
    events.append(
        SSEEvent.from_json(
            {
                "type": "message_start",
                "message": {
                    "id": msg_id,
                    "type": "message",
                    "role": "assistant",
                    "model": model,
                    "content": [],
                },
            },
            event="message_start",
        )
    )

    # 2. content_block_start
    events.append(
        SSEEvent.from_json(
            {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
            event="content_block_start",
        )
    )

    # 3. content_block_delta chunks
    words = content.split(" ")
    i = 0
    while i < len(words):
        chunk_words = words[i : i + words_per_chunk]
        prefix = " " if i > 0 else ""
        text_piece = prefix + " ".join(chunk_words)

        events.append(
            SSEEvent.from_json(
                {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": text_piece}},
                event="content_block_delta",
            )
        )
        i += words_per_chunk

    # 4. content_block_stop & message_stop
    events.append(
        SSEEvent.from_json({"type": "content_block_stop", "index": 0}, event="content_block_stop")
    )
    events.append(
        SSEEvent.from_json({"type": "message_stop"}, event="message_stop")
    )

    return events


def create_streaming_fault_transport(
    preset: str = "openai",
    sample_text: str = "RetryLab makes AI streaming resilient and fault tolerant.",
    chaos_config: StreamingChaosConfig | None = None,
    url_pattern: str | None = None,
) -> StreamingFaultTransport:
    """
    Creates a pre-configured HTTPX transport emitting simulated OpenAI or Anthropic streaming responses
    with chaos injection.
    """
    cfg = chaos_config or StreamingChaosConfig()

    if preset.lower() == "anthropic":
        raw_events = build_anthropic_messages_stream(sample_text)
        default_pattern = "api.anthropic.com"
    else:
        raw_events = build_openai_chat_stream(sample_text)
        default_pattern = "api.openai.com"

    def stream_factory(req: httpx.Request):
        return ChaosStreamGenerator(raw_events, cfg)

    return StreamingFaultTransport(
        stream_factory=stream_factory,
        url_pattern=url_pattern or default_pattern,
    )
