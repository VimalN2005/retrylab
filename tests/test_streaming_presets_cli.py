"""
Tests for streaming presets (OpenAI, Anthropic) and CLI 'retrylab stream simulate'.
"""

import json
import httpx
import pytest
from typer.testing import CliRunner

from retrylab.cli.main import app
from retrylab.streaming import (
    SSEStreamParser,
    StreamingChaosConfig,
    StreamingChaosMode,
    build_anthropic_messages_stream,
    build_openai_chat_stream,
    create_streaming_fault_transport,
)

runner = CliRunner()


def test_build_openai_chat_stream():
    events = build_openai_chat_stream("Hello world from OpenAI", model="gpt-4o")
    assert len(events) >= 3
    assert events[-1].data == "[DONE]"

    # Verify first chunk has role assistant
    first = json.loads(events[0].data)
    assert first["choices"][0]["delta"]["role"] == "assistant"


def test_build_anthropic_messages_stream():
    events = build_anthropic_messages_stream("Hello world from Anthropic", model="claude-3-5-sonnet")
    event_names = [e.event for e in events]
    assert "message_start" in event_names
    assert "content_block_start" in event_names
    assert "content_block_delta" in event_names
    assert "message_stop" in event_names


def test_create_streaming_fault_transport():
    chaos = StreamingChaosConfig(
        mode=StreamingChaosMode.TRUNCATE,
        truncate_after_chunks=2,
    )
    transport = create_streaming_fault_transport(
        preset="openai",
        sample_text="One two three four five",
        chaos_config=chaos,
    )

    client = httpx.Client(transport=transport)
    chunks_received = 0
    parser = SSEStreamParser()

    with client.stream("POST", "https://api.openai.com/v1/chat/completions") as response:
        assert response.status_code == 200
        for chunk in response.iter_bytes():
            for _ in parser.feed(chunk):
                chunks_received += 1

    assert chunks_received == 2


def test_cli_stream_help():
    result = runner.invoke(app, ["stream", "--help"])
    assert result.exit_code == 0
    assert "simulate" in result.stdout


def test_cli_stream_simulate_openai_truncate():
    result = runner.invoke(app, ["stream", "simulate", "--preset", "openai", "--chaos", "truncate", "--truncate-after", "3"])
    assert result.exit_code == 0
    assert "Simulating OPENAI Token Stream" in result.stdout
    assert "Fault Triggered: truncated_after_chunk_3" in result.stdout


def test_cli_stream_simulate_anthropic_error():
    result = runner.invoke(app, ["stream", "simulate", "--preset", "anthropic", "--chaos", "inject_error"])
    assert result.exit_code == 0
    assert "Simulating ANTHROPIC Token Stream" in result.stdout
    assert "STREAM ERROR EVENT" in result.stdout
    assert "Fault Triggered: injected_error" in result.stdout
