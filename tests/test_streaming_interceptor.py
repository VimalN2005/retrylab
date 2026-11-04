"""
Tests for SSEEvent, SSEStreamParser, and StreamingFaultTransport.
"""

import json
import httpx
import pytest

from retrylab.streaming import (
    SSEEvent,
    SSEStreamParser,
    StreamingFaultTransport,
)


def test_sse_event_encoding():
    evt = SSEEvent(
        data="hello world",
        event="message",
        id="msg_123",
        retry=5000,
    )
    wire = evt.encode()
    assert b"event: message\n" in wire
    assert b"id: msg_123\n" in wire
    assert b"retry: 5000\n" in wire
    assert b"data: hello world\n\n" in wire

    # Test from_json factory
    json_evt = SSEEvent.from_json({"text": "streaming token"}, event="chunk")
    assert json_evt.event == "chunk"
    assert json.loads(json_evt.data) == {"text": "streaming token"}


def test_sse_stream_parser_incremental():
    parser = SSEStreamParser()

    chunk_1 = b"event: update\ndata: part1"
    chunk_2 = b"\ndata: part2\n\nevent: ping\ndata: pong\n\n"

    events_1 = parser.feed(chunk_1)
    assert len(events_1) == 0  # Incomplete chunk, no double newline

    events_2 = parser.feed(chunk_2)
    assert len(events_2) == 2

    assert events_2[0].event == "update"
    assert events_2[0].data == "part1\npart2"

    assert events_2[1].event == "ping"
    assert events_2[1].data == "pong"


def test_streaming_fault_transport():
    tokens = ["The", " quick", " brown", " fox"]

    def chunk_generator(request: httpx.Request):
        for tok in tokens:
            evt = SSEEvent(data=json.dumps({"token": tok}))
            yield evt.encode()
        yield b"data: [DONE]\n\n"

    transport = StreamingFaultTransport(
        stream_factory=chunk_generator,
        url_pattern="api.openai.com",
    )

    client = httpx.Client(transport=transport)
    received_tokens = []
    parser = SSEStreamParser()

    with client.stream("POST", "https://api.openai.com/v1/chat/completions") as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        for chunk in response.iter_bytes():
            events = parser.feed(chunk)
            for e in events:
                if e.data != "[DONE]":
                    data = json.loads(e.data)
                    received_tokens.append(data["token"])

    assert received_tokens == tokens
