"""
Unit tests for 'retrylab grpc simulate' CLI command and polyglot gRPC snippet generation.
"""

from typer.testing import CliRunner

from retrylab.cli.main import app
from retrylab.matrix import PolyglotChaosMatrix

runner = CliRunner()


def test_cli_grpc_simulate_unavailable():
    """Verify 'retrylab grpc simulate' command with UNAVAILABLE fault."""
    result = runner.invoke(app, ["grpc", "simulate", "--status", "UNAVAILABLE"])
    assert result.exit_code == 0
    assert "[gRPC] Simulating Fault: UNAVAILABLE" in result.stdout
    assert "[RPC FAULT] Injected Exception: [UNAVAILABLE]" in result.stdout
    assert "retryPolicy" in result.stdout
    assert "[PASS] Recovered Cleanly" in result.stdout


def test_cli_grpc_simulate_deadline_exceeded():
    """Verify 'retrylab grpc simulate' with DEADLINE_EXCEEDED and delay."""
    result = runner.invoke(app, [
        "grpc", "simulate",
        "--method", "/search.VectorDB/Query",
        "--status", "DEADLINE_EXCEEDED",
        "--delay-ms", "10",
    ])
    assert result.exit_code == 0
    assert "[gRPC] Simulating Fault: DEADLINE_EXCEEDED" in result.stdout
    assert "/search.VectorDB/Query" in result.stdout
    assert "deadline" in result.stdout.lower()


def test_cli_grpc_simulate_resource_exhausted():
    """Verify 'retrylab grpc simulate' with RESOURCE_EXHAUSTED."""
    result = runner.invoke(app, ["grpc", "simulate", "--status", "RESOURCE_EXHAUSTED"])
    assert result.exit_code == 0
    assert "[RPC FAULT] Injected Exception: [RESOURCE_EXHAUSTED]" in result.stdout
    assert "rate limiting" in result.stdout.lower()


def test_cli_grpc_simulate_invalid_status():
    """Verify 'retrylab grpc simulate' with invalid status exits with code 1."""
    result = runner.invoke(app, ["grpc", "simulate", "--status", "NON_EXISTENT_STATUS"])
    assert result.exit_code == 1
    assert "Invalid gRPC status code" in result.stdout


def test_polyglot_grpc_snippets():
    """Verify polyglot gRPC snippet generators for Python, Go, and TypeScript."""
    py_code = PolyglotChaosMatrix.to_python_grpc_snippet(
        method="/payments.PaymentService/*",
        status="UNAVAILABLE",
        fail_count=2,
    )
    assert "GRPCStatusCode.UNAVAILABLE" in py_code
    assert "RetryLabUnaryClientInterceptor" in py_code
    assert "fail_count=2" in py_code

    go_code = PolyglotChaosMatrix.to_go_grpc_snippet(
        method="/payments.PaymentService/*",
        status="DEADLINE_EXCEEDED",
        fail_count=1,
    )
    assert "codes.DeadlineExceeded" in go_code
    assert "UnaryClientInterceptor" in go_code

    ts_code = PolyglotChaosMatrix.to_ts_grpc_snippet(
        method="/payments.PaymentService/*",
        status="RESOURCE_EXHAUSTED",
        fail_count=3,
    )
    assert "grpc.status.RESOURCE_EXHAUSTED" in ts_code
    assert "createGRPCChaosInterceptor" in ts_code
    assert "failCount: 3" in ts_code
