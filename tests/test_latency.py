"""
Tests for LatencyProfile distributions and calculations.
"""

import pytest
from retrylab import (
    FaultScenario,
    FaultType,
    LatencyDistribution,
    LatencyProfile,
)


def test_latency_fixed():
    profile = LatencyProfile(distribution=LatencyDistribution.FIXED, base_delay=0.15)
    for attempt in range(1, 5):
        assert profile.compute_delay(attempt=attempt) == 0.15


def test_latency_uniform():
    profile = LatencyProfile(
        distribution=LatencyDistribution.UNIFORM,
        min_delay=0.1,
        max_delay=0.3,
    )
    for _ in range(20):
        d = profile.compute_delay()
        assert 0.1 <= d <= 0.3


def test_latency_uniform_invalid_bounds():
    with pytest.raises(ValueError, match="min_delay cannot be greater than max_delay"):
        LatencyProfile(
            distribution=LatencyDistribution.UNIFORM,
            min_delay=0.5,
            max_delay=0.2,
        )


def test_latency_ramp():
    profile = LatencyProfile(
        distribution=LatencyDistribution.RAMP,
        base_delay=0.1,
        ramp_step=0.05,
    )
    assert pytest.approx(profile.compute_delay(attempt=1)) == 0.10
    assert pytest.approx(profile.compute_delay(attempt=2)) == 0.15
    assert pytest.approx(profile.compute_delay(attempt=3)) == 0.20


def test_latency_spike_probability_100():
    profile = LatencyProfile(
        distribution=LatencyDistribution.FIXED,
        base_delay=0.05,
        spike_probability=1.0,
        spike_delay=2.5,
    )
    assert profile.compute_delay(attempt=1) == 2.5


def test_scenario_delegates_to_latency_profile():
    profile = LatencyProfile(distribution=LatencyDistribution.FIXED, base_delay=0.25)
    scenario = FaultScenario(
        target="https://api.example.com/*",
        fault=FaultType.TIMEOUT,
        latency_profile=profile,
    )
    assert scenario.get_delay() == 0.25
