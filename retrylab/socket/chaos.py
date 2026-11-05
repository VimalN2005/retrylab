"""
RetryLab Low-Level TCP Socket Chaos & Raw Connection Fault Simulator.
Models transport-level anomalies that occur beneath the HTTP layer:
- TCP RST (ConnectionResetError / connection dropped by peer)
- Silent Blackhole Drops (packet loss leading to read timeout)
- Slow Drip Bandwidth Choking (trickle delivery to test client chunk timeouts)
- Malformed Raw Protocol Bytes (corrupt wire bytes)
- Premature Socket Closure (FIN before body completion)
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Any, Generator, Iterable
from pydantic import BaseModel, Field


class SocketFaultType(str, Enum):
    """Types of low-level socket and TCP connection faults."""

    NONE = "none"
    CONNECTION_RESET = "connection_reset"          # TCP RST / ConnectionResetError
    SILENT_DROP = "silent_drop"                    # Packet drop leading to read timeout
    SLOW_DRIP = "slow_drip"                        # Trickle chunk delivery
    MALFORMED_RAW_RESPONSE = "malformed_raw"       # Non-HTTP wire bytes
    PREMATURE_CLOSE = "premature_close"            # Socket closed mid-transmission


class SocketChaosConfig(BaseModel):
    """Configuration for socket and TCP layer chaos simulation."""

    fault_type: SocketFaultType = SocketFaultType.NONE
    drop_timeout_seconds: float = 0.5
    drip_bytes_per_chunk: int = 8
    drip_delay_seconds: float = 0.02
    raw_malformed_bytes: bytes = b"RAW_GARBAGE_TCP_PACKET\r\n\r\n"
    trigger_attempt: int = 1


class SocketFaultSimulator:
    """
    Evaluates and injects socket-level faults into payload transmission streams.
    """

    def __init__(self, config: SocketChaosConfig) -> None:
        self.config = config
        self.faults_triggered: int = 0
        self.last_fault_applied: SocketFaultType | None = None

    def should_trigger(self, attempt: int = 1) -> bool:
        """Determines if the fault should be applied on the given attempt index."""
        if self.config.fault_type == SocketFaultType.NONE:
            return False
        return self.config.trigger_attempt == attempt or self.config.trigger_attempt == 0

    def execute_stream(
        self,
        content: bytes,
        attempt: int = 1,
    ) -> Generator[bytes, None, None]:
        """
        Executes payload streaming with socket-level chaos injection.
        Yields raw byte chunks or raises low-level OS/socket exceptions.
        """
        if not self.should_trigger(attempt):
            yield content
            return

        self.faults_triggered += 1
        self.last_fault_applied = self.config.fault_type

        # 1. TCP RST (Connection Reset)
        if self.config.fault_type == SocketFaultType.CONNECTION_RESET:
            raise ConnectionResetError("Connection reset by peer (Simulated TCP RST)")

        # 2. Silent Drop (Blackhole timeout)
        elif self.config.fault_type == SocketFaultType.SILENT_DROP:
            if self.config.drop_timeout_seconds > 0:
                time.sleep(self.config.drop_timeout_seconds)
            raise TimeoutError(f"Connection timed out after {self.config.drop_timeout_seconds}s (Simulated TCP blackhole drop)")

        # 3. Slow Drip (Trickle bytes)
        elif self.config.fault_type == SocketFaultType.SLOW_DRIP:
            chunk_size = max(1, self.config.drip_bytes_per_chunk)
            for i in range(0, len(content), chunk_size):
                if i > 0 and self.config.drip_delay_seconds > 0:
                    time.sleep(self.config.drip_delay_seconds)
                yield content[i : i + chunk_size]

        # 4. Malformed Raw Bytes
        elif self.config.fault_type == SocketFaultType.MALFORMED_RAW_RESPONSE:
            yield self.config.raw_malformed_bytes

        # 5. Premature Socket Close
        elif self.config.fault_type == SocketFaultType.PREMATURE_CLOSE:
            # Yield incomplete partial slice then exit abruptly
            partial_len = min(len(content), max(4, len(content) // 2))
            yield content[:partial_len]
            return
