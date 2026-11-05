"""
Tests for SocketChaosTransport (HTTPX) and SocketChaosAdapter (Requests).
"""

import httpx
import pytest
import requests

from retrylab.socket import (
    SocketChaosAdapter,
    SocketChaosConfig,
    SocketChaosTransport,
    SocketFaultType,
)


def test_httpx_socket_chaos_connection_reset():
    cfg = SocketChaosConfig(fault_type=SocketFaultType.CONNECTION_RESET)
    transport = SocketChaosTransport(config=cfg)
    client = httpx.Client(transport=transport)

    with pytest.raises(httpx.RemoteProtocolError, match="Connection reset by peer"):
        client.get("https://api.payment.com/v1/charge")


def test_httpx_socket_chaos_silent_drop():
    cfg = SocketChaosConfig(
        fault_type=SocketFaultType.SILENT_DROP,
        drop_timeout_seconds=0.03,
    )
    transport = SocketChaosTransport(config=cfg)
    client = httpx.Client(transport=transport)

    with pytest.raises(httpx.ReadTimeout, match="Read timed out"):
        client.get("https://api.payment.com/v1/charge")


def test_httpx_socket_chaos_slow_drip():
    cfg = SocketChaosConfig(
        fault_type=SocketFaultType.SLOW_DRIP,
        drip_bytes_per_chunk=4,
        drip_delay_seconds=0.01,
    )
    transport = SocketChaosTransport(
        config=cfg,
        default_body={"message": "slow drip payload"},
    )
    client = httpx.Client(transport=transport)

    resp = client.get("https://api.payment.com/v1/charge")
    assert resp.status_code == 200
    assert resp.json() == {"message": "slow drip payload"}


def test_httpx_socket_chaos_recovery_on_retry():
    # Only fail attempt 1, recover cleanly on attempt 2
    cfg = SocketChaosConfig(
        fault_type=SocketFaultType.CONNECTION_RESET,
        trigger_attempt=1,
    )
    transport = SocketChaosTransport(
        config=cfg,
        default_body={"recovered": True},
    )
    client = httpx.Client(transport=transport)

    # Attempt 1 -> fails with connection reset
    with pytest.raises(httpx.RemoteProtocolError):
        client.get("https://api.payment.com/v1/charge")

    # Attempt 2 -> recovered!
    resp = client.get("https://api.payment.com/v1/charge")
    assert resp.status_code == 200
    assert resp.json() == {"recovered": True}


def test_requests_socket_chaos_connection_reset():
    cfg = SocketChaosConfig(fault_type=SocketFaultType.CONNECTION_RESET)
    adapter = SocketChaosAdapter(config=cfg)
    session = requests.Session()
    session.mount("https://", adapter)

    with pytest.raises(requests.exceptions.ConnectionError, match="Connection reset by peer"):
        session.get("https://api.payment.com/v1/charge")


def test_requests_socket_chaos_silent_drop():
    cfg = SocketChaosConfig(
        fault_type=SocketFaultType.SILENT_DROP,
        drop_timeout_seconds=0.03,
    )
    adapter = SocketChaosAdapter(config=cfg)
    session = requests.Session()
    session.mount("https://", adapter)

    with pytest.raises(requests.exceptions.ReadTimeout, match="Read timed out"):
        session.get("https://api.payment.com/v1/charge")


def test_requests_socket_chaos_premature_close():
    cfg = SocketChaosConfig(fault_type=SocketFaultType.PREMATURE_CLOSE)
    adapter = SocketChaosAdapter(config=cfg)
    session = requests.Session()
    session.mount("https://", adapter)

    with pytest.raises(requests.exceptions.ChunkedEncodingError, match="Connection broken"):
        session.get("https://api.payment.com/v1/charge")
