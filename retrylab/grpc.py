"""
RetryLab gRPC and Protobuf Chaos Engineering & Resilience Engine.
Provides canonical gRPC status code fault injection, client interceptors, and mock channels.
"""

from __future__ import annotations

import fnmatch
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

try:
    import grpc
    from grpc._interceptor import _UnaryOutcome
    HAS_GRPC = True
except ImportError:  # pragma: no cover
    grpc = None
    _UnaryOutcome = None
    HAS_GRPC = False


class GRPCStatusCode(str, Enum):
    """Canonical gRPC status codes (RFC 7807 / gRPC core specification)."""

    OK = "OK"
    CANCELLED = "CANCELLED"
    UNKNOWN = "UNKNOWN"
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    DEADLINE_EXCEEDED = "DEADLINE_EXCEEDED"
    NOT_FOUND = "NOT_FOUND"
    ALREADY_EXISTS = "ALREADY_EXISTS"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    RESOURCE_EXHAUSTED = "RESOURCE_EXHAUSTED"
    FAILED_PRECONDITION = "FAILED_PRECONDITION"
    ABORTED = "ABORTED"
    OUT_OF_RANGE = "OUT_OF_RANGE"
    UNIMPLEMENTED = "UNIMPLEMENTED"
    INTERNAL = "INTERNAL"
    UNAVAILABLE = "UNAVAILABLE"
    DATA_LOSS = "DATA_LOSS"
    UNAUTHENTICATED = "UNAUTHENTICATED"


def to_grpc_status(status: Union[GRPCStatusCode, str]) -> Any:
    """Convert GRPCStatusCode enum or string to native grpc.StatusCode."""
    if not HAS_GRPC:
        return status
    name = status.value if isinstance(status, GRPCStatusCode) else str(status).upper()
    try:
        return getattr(grpc.StatusCode, name)
    except AttributeError:
        return grpc.StatusCode.UNKNOWN


class DummyCall:
    """Minimal gRPC Call stub for synthetic recovery outcomes."""

    def __init__(self, code: Any = None, details: str = "", metadata: Sequence[Tuple[str, str]] = ()):
        self._code = code if code is not None else (grpc.StatusCode.OK if HAS_GRPC else "OK")
        self._details = details
        self._metadata = tuple(metadata)

    def initial_metadata(self) -> Sequence[Tuple[str, str]]:
        return ()

    def trailing_metadata(self) -> Sequence[Tuple[str, str]]:
        return self._metadata

    def code(self) -> Any:
        return self._code

    def details(self) -> str:
        return self._details

    def is_active(self) -> bool:
        return False

    def time_remaining(self) -> Optional[float]:
        return None

    def cancel(self) -> bool:
        return False

    def add_callback(self, callback: Callable) -> bool:
        return False


_RpcBase = grpc.RpcError if HAS_GRPC else Exception
_CallBase = grpc.Call if HAS_GRPC else object


class SimulatedGRPCError(_RpcBase, _CallBase):
    """Simulated gRPC RpcError carrying canonical status code, details, and trailing metadata."""

    def __init__(
        self,
        code: Union[GRPCStatusCode, Any],
        details: str = "Simulated gRPC failure",
        trailing_metadata: Sequence[Tuple[str, str]] = (),
    ):
        self._code = code
        self._details = details
        self._trailing_metadata = tuple(trailing_metadata)
        code_str = getattr(code, "name", str(code))
        super().__init__(f"Simulated gRPC Error: [{code_str}] {details}")

    def code(self) -> Any:
        return self._code

    def details(self) -> str:
        return self._details

    def trailing_metadata(self) -> Sequence[Tuple[str, str]]:
        return self._trailing_metadata

    def initial_metadata(self) -> Sequence[Tuple[str, str]]:
        return ()

    def is_active(self) -> bool:
        return False

    def time_remaining(self) -> Optional[float]:
        return None

    def cancel(self) -> bool:
        return False


@dataclass
class GRPCRecordedCall:
    """Record of an intercepted gRPC RPC call."""

    method: str
    request: Any
    metadata: Sequence[Tuple[str, str]]
    timestamp: float
    attempt: int
    was_fault_injected: bool
    injected_status: Optional[str] = None


@dataclass
class GRPCFaultConfig:
    """Configuration for gRPC fault injection and recovery."""

    method_pattern: str = "*"
    status_code: GRPCStatusCode = GRPCStatusCode.UNAVAILABLE
    details: str = "Simulated gRPC downstream failure"
    trailing_metadata: Sequence[Tuple[str, str]] = field(default_factory=tuple)
    fail_count: int = 1
    delay_ms: float = 0.0
    recover_response: Any = b'{"status": "ok"}'


_InterceptorBase = grpc.UnaryUnaryClientInterceptor if HAS_GRPC else object


class RetryLabUnaryClientInterceptor(_InterceptorBase):
    """In-process gRPC Unary-Unary Client Interceptor for fault injection & recovery verification."""

    def __init__(self, config: Optional[GRPCFaultConfig] = None):
        self.config = config or GRPCFaultConfig()
        self._attempts = 0
        self._history: List[GRPCRecordedCall] = []
        self._lock = threading.Lock()

    def reset(self) -> None:
        """Reset attempts counter and call history."""
        with self._lock:
            self._attempts = 0
            self._history.clear()

    @property
    def attempts(self) -> int:
        return self._attempts

    @property
    def history(self) -> List[GRPCRecordedCall]:
        with self._lock:
            return list(self._history)

    def _matches(self, method: str) -> bool:
        """Verify whether target method matches the pattern."""
        pattern = self.config.method_pattern
        if pattern == "*" or pattern == "/*":
            return True
        if pattern.endswith("*"):
            prefix = pattern[:-1]
            return method.startswith(prefix) or fnmatch.fnmatch(method, pattern)
        return method == pattern or fnmatch.fnmatch(method, pattern)

    def intercept_unary_unary(
        self,
        continuation: Callable,
        client_call_details: Any,
        request: Any,
    ) -> Any:
        """Intercept unary RPC call, inject configured fault or simulate recovery."""
        method = getattr(client_call_details, "method", str(client_call_details))
        metadata = getattr(client_call_details, "metadata", ()) or ()

        if not self._matches(method):
            return continuation(client_call_details, request)

        with self._lock:
            self._attempts += 1
            current_attempt = self._attempts

        # Inject latency if configured
        if self.config.delay_ms > 0:
            time.sleep(self.config.delay_ms / 1000.0)

        # Fault injection phase
        if current_attempt <= self.config.fail_count:
            native_code = to_grpc_status(self.config.status_code)
            with self._lock:
                self._history.append(
                    GRPCRecordedCall(
                        method=method,
                        request=request,
                        metadata=metadata,
                        timestamp=time.time(),
                        attempt=current_attempt,
                        was_fault_injected=True,
                        injected_status=self.config.status_code.value,
                    )
                )
            raise SimulatedGRPCError(
                code=native_code,
                details=self.config.details,
                trailing_metadata=self.config.trailing_metadata,
            )

        # Recovery phase
        with self._lock:
            self._history.append(
                GRPCRecordedCall(
                    method=method,
                    request=request,
                    metadata=metadata,
                    timestamp=time.time(),
                    attempt=current_attempt,
                    was_fault_injected=False,
                    injected_status=None,
                )
            )

        if self.config.recover_response is not None and HAS_GRPC:
            return _UnaryOutcome(self.config.recover_response, DummyCall())
        elif self.config.recover_response is not None:
            return self.config.recover_response

        return continuation(client_call_details, request)


def create_intercepted_channel(
    target: str = "localhost:50051",
    config: Optional[GRPCFaultConfig] = None,
    options: Optional[Sequence[Tuple[str, Any]]] = None,
) -> Any:
    """Create a gRPC insecure channel wrapped with RetryLab fault injection interceptor."""
    if not HAS_GRPC:
        raise RuntimeError("grpcio package is required to create a native gRPC channel.")
    interceptor = RetryLabUnaryClientInterceptor(config=config)
    base_channel = grpc.insecure_channel(target, options=options)
    return grpc.intercept_channel(base_channel, interceptor)


def get_grpc_recommendation(status: Union[GRPCStatusCode, str]) -> str:
    """Return tailored reliability recommendations for canonical gRPC errors."""
    name = status.value if isinstance(status, GRPCStatusCode) else str(status).upper()

    recommendations = {
        "UNAVAILABLE": (
            "Configure gRPC client retry policy (`service_config.json` with `retryPolicy.maxAttempts`, "
            "`initialBackoff`, `backoffMultiplier`, `retryableStatusCodes=['UNAVAILABLE']`)."
        ),
        "DEADLINE_EXCEEDED": (
            "Tune per-RPC call deadline (`stub.Method(request, timeout=...)`) to avoid thread starvation, "
            "and propagate context deadlines across microservice boundaries."
        ),
        "RESOURCE_EXHAUSTED": (
            "Implement client-side token bucket rate limiting and exponential backoff; "
            "inspect `retry-delay-ms` trailing metadata."
        ),
        "INTERNAL": (
            "Verify downstream server error logs and crash handlers; only retry if transaction is idempotent "
            "and protected by persistent unique idempotency tokens."
        ),
        "FAILED_PRECONDITION": (
            "System state mismatch. Do not blindly retry; query system state (e.g. account active/balance) "
            "before issuing subsequent requests."
        ),
        "UNAUTHENTICATED": (
            "Refresh OAuth2 / JWT bearer tokens automatically upon receiving UNAUTHENTICATED status before retrying."
        ),
    }

    return recommendations.get(
        name,
        "Implement exponential backoff with jitter and verify retry idempotency guarantees."
    )
