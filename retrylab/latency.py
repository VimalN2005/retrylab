"""
RetryLab Dynamic Latency & Jitter Profiles.
Simulates realistic production network conditions (jitter, spikes, degradation).
"""

from __future__ import annotations

import random
from enum import Enum
from pydantic import BaseModel, Field, model_validator


class LatencyDistribution(str, Enum):
    """Distribution models for simulated network latency."""

    FIXED = "fixed"
    UNIFORM = "uniform"
    NORMAL = "normal"
    SPIKE = "spike"
    RAMP = "ramp"


class LatencyProfile(BaseModel):
    """
    Configures realistic latency generation.

    Attributes:
        distribution: Type of distribution (FIXED, UNIFORM, NORMAL, SPIKE, RAMP)
        base_delay: Constant delay in seconds (for FIXED distribution)
        min_delay: Minimum delay in seconds (for UNIFORM distribution)
        max_delay: Maximum delay in seconds (for UNIFORM distribution)
        mean_delay: Expected mean delay in seconds (for NORMAL distribution)
        std_dev: Standard deviation in seconds (for NORMAL distribution)
        spike_probability: Probability (0.0 to 1.0) of a sudden latency spike
        spike_delay: Delay duration in seconds when a spike triggers
        ramp_step: Additional delay in seconds added with each consecutive attempt
    """

    distribution: LatencyDistribution = LatencyDistribution.FIXED
    base_delay: float = Field(default=0.0, ge=0.0)
    min_delay: float = Field(default=0.0, ge=0.0)
    max_delay: float = Field(default=0.0, ge=0.0)
    mean_delay: float = Field(default=0.0, ge=0.0)
    std_dev: float = Field(default=0.0, ge=0.0)
    spike_probability: float = Field(default=0.0, ge=0.0, le=1.0)
    spike_delay: float = Field(default=0.0, ge=0.0)
    ramp_step: float = Field(default=0.0, ge=0.0)

    @model_validator(mode="after")
    def validate_bounds(self) -> LatencyProfile:
        if self.distribution == LatencyDistribution.UNIFORM:
            if self.min_delay > self.max_delay:
                raise ValueError("min_delay cannot be greater than max_delay")
        return self

    def compute_delay(self, attempt: int = 1) -> float:
        """
        Calculates the simulated latency for a specific attempt number.
        Returns duration in seconds (always >= 0.0).
        """
        # 1. Check for random latency spike regardless of distribution
        if self.spike_probability > 0.0 and random.random() < self.spike_probability:
            return max(0.0, self.spike_delay)

        # 2. Compute base distribution delay
        computed: float = 0.0

        if self.distribution == LatencyDistribution.FIXED:
            computed = self.base_delay

        elif self.distribution == LatencyDistribution.UNIFORM:
            computed = random.uniform(self.min_delay, self.max_delay)

        elif self.distribution == LatencyDistribution.NORMAL:
            # Gaussian / normal distribution, clamped at 0
            computed = max(0.0, random.gauss(self.mean_delay, self.std_dev))

        elif self.distribution == LatencyDistribution.SPIKE:
            # Pure spike mode: default to base_delay unless spike occurs
            computed = self.base_delay

        elif self.distribution == LatencyDistribution.RAMP:
            # Progressively degrades with each consecutive retry/attempt
            computed = self.base_delay + (max(0, attempt - 1) * self.ramp_step)

        return max(0.0, computed)
