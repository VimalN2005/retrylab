"""
RetryLab Streaming Chaos & Server-Sent Events (SSE) Disruption Module.
"""

from retrylab.streaming.interceptor import (
    SSEEvent,
    SSEStreamParser,
    StreamingByteIterator,
    StreamingFaultTransport,
)
from retrylab.streaming.chaos import (
    ChaosStreamGenerator,
    StreamingChaosConfig,
    StreamingChaosMode,
)
from retrylab.streaming.presets import (
    build_anthropic_messages_stream,
    build_openai_chat_stream,
    create_streaming_fault_transport,
)

__all__ = [
    "SSEEvent",
    "SSEStreamParser",
    "StreamingByteIterator",
    "StreamingFaultTransport",
    "ChaosStreamGenerator",
    "StreamingChaosConfig",
    "StreamingChaosMode",
    "build_openai_chat_stream",
    "build_anthropic_messages_stream",
    "create_streaming_fault_transport",
]
