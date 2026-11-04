"""
Tests for ChaosStreamGenerator and StreamingFaultTransport failure modes.
"""

import json
import time
import httpx
import pytest

from retrylab.streaming import (
    ChaosStreamGenerator,
    SSEEvent,
    SSEStreamParser,
    StreamingChaosConfig,
    StreamingChaosMode,
    StreamingFaultTransport,
)


def _sample_events(count: int = 5) -> list[SSEEvent]:
    return [
        SSEEvent.from_json({"chunk": i, "content": f"token_{i}"})
        for i in range(1, count + 1)
    ]


def test_streaming_chaos_truncate():
    events = _sample_events(5)
    config = StreamingChaosConfig(
        mode=StreamingChaosMode.TRUNCATE,
        truncate_after_chunks=3,
    )

    gen = ChaosStreamGenerator(events, config)
    emitted = list(gen)

    assert len(emitted) == 3
    assert gen.chunks_emitted == 3
    assert "truncated_after_chunk_3" in (gen.fault_injected or "")

    parser = SSEStreamParser()
    parsed_events = []
    for chunk in emitted:
        parsed_events.extend(parser.feed(chunk))

    assert len(parsed_events) == 3
    assert json.loads(parsed_events[-1].data)["chunk"] == 3


def test_streaming_chaos_drop_chunks():
    events = _sample_events(5)
    config = StreamingChaosConfig(
        mode=StreamingChaosMode.DROP_CHUNKS,
        drop_chunk_indices=[2, 4],
    )

    gen = ChaosStreamGenerator(events, config)
    emitted = list(gen)

    assert len(emitted) == 3
    assert gen.chunks_dropped == 2

    parser = SSEStreamParser()
    parsed_events = []
    for chunk in emitted:
        parsed_events.extend(parser.feed(chunk))

    chunks_seen = [json.loads(e.data)["chunk"] for e in parsed_events]
    assert chunks_seen == [1, 3, 5]


def test_streaming_chaos_corrupt_json():
    events = _sample_events(4)
    config = StreamingChaosConfig(
        mode=StreamingChaosMode.CORRUPT_JSON,
        corrupt_chunk_index=2,
    )

    gen = ChaosStreamGenerator(events, config)
    emitted = list(gen)
    assert len(emitted) == 4

    parser = SSEStreamParser()
    parsed_events = []
    failed_json_count = 0

    for chunk in emitted:
        for ev in parser.feed(chunk):
            try:
                json.loads(ev.data)
                parsed_events.append(ev)
            except Exception:
                failed_json_count += 1

    assert failed_json_count >= 1
    assert "corrupted_chunk_2" in (gen.fault_injected or "")


def test_streaming_chaos_stall():
    events = _sample_events(3)
    config = StreamingChaosConfig(
        mode=StreamingChaosMode.MID_STREAM_STALL,
        stall_after_chunk=1,
        stall_seconds=0.05,
    )

    gen = ChaosStreamGenerator(events, config)
    t0 = time.time()
    emitted = list(gen)
    elapsed = time.time() - t0

    assert len(emitted) == 3
    assert elapsed >= 0.04
    assert "stalled" in (gen.fault_injected or "")


def test_streaming_chaos_inject_error():
    events = _sample_events(5)
    config = StreamingChaosConfig(
        mode=StreamingChaosMode.INJECT_ERROR,
        corrupt_chunk_index=2,
    )

    gen = ChaosStreamGenerator(events, config)
    emitted = list(gen)

    # Chunk 1 emitted, Chunk 2 is error event, stream terminates
    assert len(emitted) == 2
    assert "injected_error" in (gen.fault_injected or "")

    parser = SSEStreamParser()
    parsed = []
    for chunk in emitted:
        parsed.extend(parser.feed(chunk))

    assert len(parsed) == 2
    assert parsed[1].event == "error"
    err_data = json.loads(parsed[1].data)
    assert "error" in err_data
    assert err_data["error"]["code"] == 503


def test_streaming_chaos_with_httpx_transport():
    events = _sample_events(6)
    config = StreamingChaosConfig(
        mode=StreamingChaosMode.TRUNCATE,
        truncate_after_chunks=4,
    )

    def stream_factory(req: httpx.Request):
        return ChaosStreamGenerator(events, config)

    transport = StreamingFaultTransport(stream_factory=stream_factory)
    client = httpx.Client(transport=transport)

    collected = []
    parser = SSEStreamParser()

    with client.stream("POST", "http://ai-api.local/v1/chat/completions") as response:
        for chunk in response.iter_bytes():
            for ev in parser.feed(chunk):
                collected.append(json.loads(ev.data)["chunk"])

    assert collected == [1, 2, 3, 4]
