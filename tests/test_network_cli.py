"""
Tests for Network Layer Chaos CLI and Polyglot Matrix DNS/TLS Extensions.
"""

from typer.testing import CliRunner

from retrylab.cli.main import app
from retrylab.matrix import PolyglotChaosMatrix, PolyglotScenarioSchema

runner = CliRunner()


def test_cli_network_simulate_dns_failure():
    """Verify `retrylab network simulate --fault dns_failure` command."""
    result = runner.invoke(app, ["network", "simulate", "--fault", "dns_failure"])
    assert result.exit_code == 0
    assert "DNS_FAILURE" in result.stdout
    assert "ConnectError" in result.stdout
    assert "Recovered Cleanly: HTTP 200" in result.stdout


def test_cli_network_simulate_ssl_cert_verification_failed():
    """Verify `retrylab network simulate --fault ssl_cert_verification_failed` command."""
    result = runner.invoke(app, ["network", "simulate", "--fault", "ssl_cert_verification_failed"])
    assert result.exit_code == 0
    assert "SSL_CERT_VERIFICATION_FAILED" in result.stdout
    assert "CERTIFICATE_VERIFY_FAILED" in result.stdout
    assert "Recovered Cleanly" in result.stdout


def test_cli_network_simulate_tls_timeout():
    """Verify `retrylab network simulate --fault tls_handshake_timeout` command."""
    result = runner.invoke(app, ["network", "simulate", "--fault", "tls_handshake_timeout"])
    assert result.exit_code == 0
    assert "TLS_HANDSHAKE_TIMEOUT" in result.stdout
    assert "ConnectTimeout" in result.stdout


def test_cli_network_simulate_invalid_fault():
    """Verify `retrylab network simulate` exits with code 1 on unknown fault."""
    result = runner.invoke(app, ["network", "simulate", "--fault", "non_existent_fault"])
    assert result.exit_code == 1
    assert "Invalid network fault" in result.stdout


def test_polyglot_matrix_dns_tls_compatibility():
    """Verify PolyglotChaosMatrix generates valid Go, TypeScript, and Python snippets for DNS/TLS faults."""
    schema = PolyglotScenarioSchema(
        name="dns_resilience_test",
        url_pattern="https://api.stripe.com/v1/charges",
        method="POST",
        fault="dns_failure",
        fail_count=2,
    )

    valid, violations = PolyglotChaosMatrix.verify_compatibility(schema)
    assert valid is True
    assert len(violations) == 0

    go_code = PolyglotChaosMatrix.to_go_snippet(schema)
    assert "retrylab.Scenario" in go_code
    assert "FaultDisconnect" in go_code

    ts_code = PolyglotChaosMatrix.to_ts_snippet(schema)
    assert 'fault: "dns_failure"' in ts_code

    py_code = PolyglotChaosMatrix.to_python_snippet(schema)
    assert "FaultType.DNS_FAILURE" in py_code
