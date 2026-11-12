"""
Tests for RetryLab Soak & Stress Testing Engine (retrylab.soak).
"""

from __future__ import annotations

from rich.table import Table

from retrylab.soak import (
    RequestSample,
    SoakConfig,
    SoakFaultMode,
    SoakResult,
    calculate_storm_severity,
    render_soak_table,
    run_soak_test,
)


def test_soak_config_defaults_and_serialization():
    """Verify SoakConfig defaults and dictionary conversion."""
    cfg = SoakConfig()
    assert cfg.duration_seconds == 3.0
    assert cfg.concurrency == 10
    assert cfg.failure_rate == 0.35
    assert cfg.max_retries == 3
    assert cfg.fault_mode == SoakFaultMode.MIXED_STORM

    d = cfg.to_dict()
    assert d["concurrency"] == 10
    assert d["fault_mode"] == "MIXED_STORM"
    assert d["burst_enabled"] is True


def test_calculate_storm_severity_thresholds():
    """Verify categorization of traffic amplification factors."""
    assert calculate_storm_severity(1.05) == "NORMAL"
    assert calculate_storm_severity(1.29) == "NORMAL"
    assert calculate_storm_severity(1.30) == "ELEVATED"
    assert calculate_storm_severity(1.95) == "ELEVATED"
    assert calculate_storm_severity(2.00) == "DANGEROUS"
    assert calculate_storm_severity(3.49) == "DANGEROUS"
    assert calculate_storm_severity(3.50) == "CRITICAL"
    assert calculate_storm_severity(5.80) == "CRITICAL"


def test_run_soak_test_quick_execution():
    """Verify execution of quick soak test with concurrent workers."""
    cfg = SoakConfig(
        duration_seconds=0.6,
        concurrency=4,
        request_interval_ms=5.0,
        failure_rate=0.25,
        max_retries=2,
        seed=101,
    )
    result = run_soak_test(cfg)

    assert isinstance(result, SoakResult)
    assert result.duration_seconds >= 0.5
    assert result.concurrency == 4
    assert result.total_user_requests > 0
    assert result.total_network_attempts >= result.total_user_requests
    assert result.storm_amplification_factor >= 1.0
    assert result.storm_severity in ["NORMAL", "ELEVATED", "DANGEROUS", "CRITICAL"]
    assert result.throughput_rps > 0.0
    assert result.p50_latency_ms > 0.0
    assert result.max_latency_ms >= result.p50_latency_ms
    assert len(result.samples) == result.total_network_attempts

    # Verify dictionary serialization
    res_dict = result.to_dict()
    assert "storm_amplification_factor" in res_dict
    assert "latency" in res_dict
    assert "status_distribution" in res_dict
    assert "memory" in res_dict


def test_run_soak_test_high_failure_rate_amplification():
    """Verify that high failure rate triggers retry attempts and amplifies traffic."""
    cfg = SoakConfig(
        duration_seconds=0.6,
        concurrency=3,
        request_interval_ms=5.0,
        failure_rate=0.75,  # 75% injected faults
        max_retries=3,
        seed=202,
    )
    result = run_soak_test(cfg)

    # With 75% failure rate and 3 retries, storm amplification factor must exceed 1.1x
    assert result.storm_amplification_factor > 1.10
    assert result.total_network_attempts > result.total_user_requests
    assert result.failed_requests + result.recovered_requests > 0


def test_run_soak_test_with_custom_callable():
    """Verify soak test with deterministic custom backend callable."""
    # Attempt 1: 503, Attempt 2: 200
    def custom_backend(worker_id: int, attempt: int):
        if attempt == 1:
            return 503, "Cluster Outage", 10.0
        return 200, None, 5.0

    cfg = SoakConfig(
        duration_seconds=0.5,
        concurrency=2,
        request_interval_ms=5.0,
        max_retries=1,
    )
    result = run_soak_test(cfg, client_callable=custom_backend)

    assert result.total_user_requests > 0
    # Every request failed attempt 1 and recovered attempt 2
    assert result.successful_requests == 0
    assert result.recovered_requests == result.total_user_requests
    assert result.failed_requests == 0
    assert result.recovery_rate == 100.0
    assert result.storm_amplification_factor == 2.0


def test_render_soak_table_formatting():
    """Verify Rich table generation from SoakResult."""
    cfg = SoakConfig(duration_seconds=0.5, concurrency=2, request_interval_ms=5.0, seed=303)
    result = run_soak_test(cfg)
    table = render_soak_table(result)

    assert isinstance(table, Table)
    assert "RetryLab Soak & Stress Test Report" in str(table.title)
    assert len(table.rows) >= 6


def test_soak_fault_modes_generation():
    """Verify execution across different fault modes."""
    modes = [
        SoakFaultMode.RATE_LIMIT_429,
        SoakFaultMode.SERVICE_UNAVAILABLE_503,
        SoakFaultMode.TIMEOUT,
        SoakFaultMode.CONNECTION_RESET,
    ]
    for mode in modes:
        cfg = SoakConfig(
            duration_seconds=0.4,
            concurrency=2,
            request_interval_ms=5.0,
            failure_rate=0.8,
            fault_mode=mode,
            seed=404,
        )
        result = run_soak_test(cfg)
        assert result.total_network_attempts > 0
