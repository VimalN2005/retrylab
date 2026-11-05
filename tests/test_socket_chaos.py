"""
Tests for SocketFaultSimulator and raw TCP/socket chaos.
"""

import time
import pytest

from retrylab.socket import (
    SocketChaosConfig,
    SocketFaultSimulator,
    SocketFaultType,
)


def test_socket_chaos_connection_reset():
    config = SocketChaosConfig(fault_type=SocketFaultType.CONNECTION_RESET)
    sim = SocketFaultSimulator(config)

    with pytest.raises(ConnectionResetError, match="Connection reset by peer"):
        list(sim.execute_stream(b"HTTP/1.1 200 OK\r\n\r\nhello"))

    assert sim.faults_triggered == 1
    assert sim.last_fault_applied == SocketFaultType.CONNECTION_RESET


def test_socket_chaos_silent_drop():
    config = SocketChaosConfig(
        fault_type=SocketFaultType.SILENT_DROP,
        drop_timeout_seconds=0.05,
    )
    sim = SocketFaultSimulator(config)

    t0 = time.time()
    with pytest.raises(TimeoutError, match=r"(?i)simulated TCP blackhole drop"):
        list(sim.execute_stream(b"HTTP/1.1 200 OK\r\n\r\nhello"))

    elapsed = time.time() - t0
    assert elapsed >= 0.04
    assert sim.faults_triggered == 1


def test_socket_chaos_slow_drip():
    content = b"1234567890abcdef"
    config = SocketChaosConfig(
        fault_type=SocketFaultType.SLOW_DRIP,
        drip_bytes_per_chunk=4,
        drip_delay_seconds=0.01,
    )
    sim = SocketFaultSimulator(config)

    chunks = list(sim.execute_stream(content))
    assert len(chunks) == 4
    assert b"".join(chunks) == content
    assert sim.faults_triggered == 1


def test_socket_chaos_malformed_raw():
    config = SocketChaosConfig(
        fault_type=SocketFaultType.MALFORMED_RAW_RESPONSE,
        raw_malformed_bytes=b"CORRUPT_TCP_STREAM_X",
    )
    sim = SocketFaultSimulator(config)

    chunks = list(sim.execute_stream(b"valid content"))
    assert len(chunks) == 1
    assert chunks[0] == b"CORRUPT_TCP_STREAM_X"


def test_socket_chaos_premature_close():
    content = b"HTTP/1.1 200 OK\r\nContent-Length: 100\r\n\r\nFull payload here"
    config = SocketChaosConfig(fault_type=SocketFaultType.PREMATURE_CLOSE)
    sim = SocketFaultSimulator(config)

    chunks = list(sim.execute_stream(content))
    partial = b"".join(chunks)
    assert len(partial) < len(content)
    assert content.startswith(partial)


def test_socket_chaos_attempt_filtering():
    config = SocketChaosConfig(
        fault_type=SocketFaultType.CONNECTION_RESET,
        trigger_attempt=2,
    )
    sim = SocketFaultSimulator(config)

    # Attempt 1: passes through untouched
    res1 = list(sim.execute_stream(b"Attempt 1 data", attempt=1))
    assert res1 == [b"Attempt 1 data"]
    assert sim.faults_triggered == 0

    # Attempt 2: raises ConnectionResetError
    with pytest.raises(ConnectionResetError):
        list(sim.execute_stream(b"Attempt 2 data", attempt=2))
    assert sim.faults_triggered == 1
