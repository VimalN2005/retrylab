"""
Unit tests for RetryLab gRPC fault injection and client interceptor engine.
"""

import time
import grpc
import pytest

from retrylab.grpc import (
    GRPCFaultConfig,
    GRPCStatusCode,
    RetryLabUnaryClientInterceptor,
    SimulatedGRPCError,
    create_intercepted_channel,
    get_grpc_recommendation,
    to_grpc_status,
)


def test_grpc_status_code_conversion():
    """Verify conversion of enum and string to native grpc.StatusCode."""
    assert to_grpc_status(GRPCStatusCode.UNAVAILABLE) == grpc.StatusCode.UNAVAILABLE
    assert to_grpc_status(GRPCStatusCode.DEADLINE_EXCEEDED) == grpc.StatusCode.DEADLINE_EXCEEDED
    assert to_grpc_status("RESOURCE_EXHAUSTED") == grpc.StatusCode.RESOURCE_EXHAUSTED
    assert to_grpc_status("unknown_custom_code") == grpc.StatusCode.UNKNOWN


def test_simulated_grpc_error_properties():
    """Verify SimulatedGRPCError satisfies gRPC RpcError and Call contracts."""
    err = SimulatedGRPCError(
        code=grpc.StatusCode.RESOURCE_EXHAUSTED,
        details="Rate limit exceeded",
        trailing_metadata=(("retry-delay-ms", "500"),),
    )

    assert isinstance(err, grpc.RpcError)
    assert isinstance(err, grpc.Call)
    assert err.code() == grpc.StatusCode.RESOURCE_EXHAUSTED
    assert err.details() == "Rate limit exceeded"
    assert err.trailing_metadata() == (("retry-delay-ms", "500"),)
    assert "RESOURCE_EXHAUSTED" in str(err)


def test_grpc_interceptor_unavailable_and_recovery():
    """Verify interceptor fails with UNAVAILABLE on attempt 1, then recovers on attempt 2."""
    config = GRPCFaultConfig(
        method_pattern="/payment.PaymentService/*",
        status_code=GRPCStatusCode.UNAVAILABLE,
        details="Payment backend cluster unreachable",
        fail_count=1,
        recover_response=b'{"charge_id": "ch_mock_999", "status": "succeeded"}',
    )
    interceptor = RetryLabUnaryClientInterceptor(config=config)

    base_channel = grpc.insecure_channel("localhost:50051")
    channel = grpc.intercept_channel(base_channel, interceptor)
    unary_call = channel.unary_unary("/payment.PaymentService/ProcessPayment")

    # Attempt 1: Expect SimulatedGRPCError (UNAVAILABLE)
    with pytest.raises(grpc.RpcError) as exc_info:
        unary_call(b'{"amount": 5000}')

    assert exc_info.value.code() == grpc.StatusCode.UNAVAILABLE
    assert "Payment backend cluster unreachable" in exc_info.value.details()
    assert interceptor.attempts == 1

    # Attempt 2: Recovers smoothly with configured response
    recovered_res = unary_call(b'{"amount": 5000}')
    assert recovered_res == b'{"charge_id": "ch_mock_999", "status": "succeeded"}'
    assert interceptor.attempts == 2

    # Verify history
    history = interceptor.history
    assert len(history) == 2
    assert history[0].was_fault_injected is True
    assert history[0].injected_status == "UNAVAILABLE"
    assert history[1].was_fault_injected is False


def test_grpc_interceptor_deadline_exceeded_with_delay():
    """Verify interceptor injects delay and DEADLINE_EXCEEDED."""
    config = GRPCFaultConfig(
        method_pattern="/vector.VectorDB/Search",
        status_code=GRPCStatusCode.DEADLINE_EXCEEDED,
        details="Vector search deadline exceeded after index scan",
        fail_count=1,
        delay_ms=20.0,
        recover_response=b'{"results": []}',
    )
    interceptor = RetryLabUnaryClientInterceptor(config=config)

    channel = grpc.intercept_channel(grpc.insecure_channel("localhost:50051"), interceptor)
    unary_call = channel.unary_unary("/vector.VectorDB/Search")

    t0 = time.perf_counter()
    with pytest.raises(grpc.RpcError) as exc_info:
        unary_call(b'{"query": "embedding"}')
    elapsed = (time.perf_counter() - t0) * 1000.0

    assert elapsed >= 15.0  # Injected delay was respected
    assert exc_info.value.code() == grpc.StatusCode.DEADLINE_EXCEEDED


def test_grpc_interceptor_non_matching_method_passthrough():
    """Verify methods that do not match the pattern are bypassed to continuation."""
    config = GRPCFaultConfig(
        method_pattern="/orders.*",
        status_code=GRPCStatusCode.INTERNAL,
    )
    interceptor = RetryLabUnaryClientInterceptor(config=config)

    class MockDetails:
        method = "/users.UserService/GetUser"
        metadata = ()

    called = False

    def mock_continuation(details, req):
        nonlocal called
        called = True
        return b"passthrough_success"

    res = interceptor.intercept_unary_unary(mock_continuation, MockDetails(), b"ping")
    assert called is True
    assert res == b"passthrough_success"
    assert interceptor.attempts == 0  # Was not incremented because method was bypassed


def test_grpc_interceptor_reset():
    """Verify interceptor reset clears attempt counter and history."""
    config = GRPCFaultConfig(method_pattern="*", fail_count=2)
    interceptor = RetryLabUnaryClientInterceptor(config=config)
    channel = grpc.intercept_channel(grpc.insecure_channel("localhost:50051"), interceptor)
    unary_call = channel.unary_unary("/test.Service/Method")

    with pytest.raises(grpc.RpcError):
        unary_call(b"test")

    assert interceptor.attempts == 1
    assert len(interceptor.history) == 1

    interceptor.reset()
    assert interceptor.attempts == 0
    assert len(interceptor.history) == 0


def test_grpc_recommendations():
    """Verify contextual recommendations for various gRPC status codes."""
    rec_unavail = get_grpc_recommendation(GRPCStatusCode.UNAVAILABLE)
    assert "retryPolicy" in rec_unavail

    rec_deadline = get_grpc_recommendation(GRPCStatusCode.DEADLINE_EXCEEDED)
    assert "deadline" in rec_deadline.lower()

    rec_resource = get_grpc_recommendation("RESOURCE_EXHAUSTED")
    assert "rate limiting" in rec_resource.lower()
