"""
Tests for RetryLab Interactive Guided Resilience Tour (retrylab.tour).
"""

from __future__ import annotations

from rich.table import Table

from retrylab.tour import (
    RetryLabTour,
    TourLessonResult,
    TourStep,
    get_all_tour_steps,
    get_tour_step_by_number,
    render_completion_summary,
)


def test_get_all_tour_steps():
    """Verify tour includes exactly 5 ordered stops."""
    steps = get_all_tour_steps()
    assert len(steps) == 5
    step_nums = [s.step_number for s in steps]
    assert step_nums == [1, 2, 3, 4, 5]

    step_ids = [s.id for s in steps]
    assert len(set(step_ids)) == 5
    assert "rate_limit_recovery" in step_ids
    assert "idempotency_shield" in step_ids
    assert "streaming_chaos" in step_ids
    assert "grpc_faults" in step_ids
    assert "storm_amplification" in step_ids


def test_get_tour_step_by_number():
    """Verify lookup by step index."""
    s1 = get_tour_step_by_number(1)
    assert s1 is not None
    assert s1.id == "rate_limit_recovery"

    s3 = get_tour_step_by_number(3)
    assert s3 is not None
    assert s3.id == "streaming_chaos"

    assert get_tour_step_by_number(99) is None
    assert get_tour_step_by_number(0) is None


def test_tour_step_serialization():
    """Verify TourStep to_dict produces clean schema for IDE / documentation tooling."""
    step = get_tour_step_by_number(2)
    assert step is not None

    d = step.to_dict()
    assert d["step_number"] == 2
    assert d["id"] == "idempotency_shield"
    assert "IdempotencyAuditor" in d["code_example"]
    assert len(d["key_takeaway"]) > 10


def test_run_tour_full_auto_mode():
    """Verify automated execution of all 5 tour lessons."""
    tour = RetryLabTour()
    results = tour.run_tour(auto_mode=True, speed=5.0)

    assert len(results) == 5
    for r in results:
        assert isinstance(r, TourLessonResult)
        assert r.passed is True
        assert r.duration_ms >= 0.0
        assert len(r.metrics) > 0


def test_run_single_tour_step():
    """Verify running a single targeted tour step."""
    tour = RetryLabTour()
    results = tour.run_tour(auto_mode=True, step_number=4, speed=5.0)

    assert len(results) == 1
    r = results[0]
    assert r.step_number == 4
    assert r.id == "grpc_faults"
    assert "status_code" in r.metrics


def test_render_completion_summary_table():
    """Verify generation of Rich scorecard summary table."""
    tour = RetryLabTour()
    results = tour.run_tour(auto_mode=True, speed=5.0)
    table = render_completion_summary(results)

    assert isinstance(table, Table)
    assert "RetryLab Tour Completion Scorecard" in str(table.title)
    assert len(table.rows) == 5


def test_individual_step_simulations():
    """Verify simulation logic for each of the 5 resilience lessons."""
    steps = get_all_tour_steps()

    # Step 1: Rate Limiting
    m1 = steps[0].simulation_fn()
    assert m1["recovery"] is True
    assert m1["attempt_1"]["status"] == 429
    assert m1["attempt_2"]["status"] == 200

    # Step 2: Idempotency
    m2 = steps[1].simulation_fn()
    assert m2["double_charge_prevented"] is True
    assert m2["key_reused"] is True
    assert m2["payload_mutated"] is False

    # Step 3: Streaming
    m3 = steps[2].simulation_fn()
    assert m3["stream_complete"] is True
    assert m3["resumed_at_token"] == 9

    # Step 4: gRPC
    m4 = steps[3].simulation_fn()
    assert m4["intercepted"] is True
    assert "UNAVAILABLE" in m4["status_code"]

    # Step 5: Storm
    m5 = steps[4].simulation_fn()
    assert m5["thundering_herd_prevented"] is True
    assert m5["storm_amplification_factor"] < 1.30
