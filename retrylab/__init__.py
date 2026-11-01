"""
RetryLab: Deterministic Third-Party API Failure Simulation & Resilience Testing Engine.
"""

from retrylab.adapters.requests_adapter import RetryLabAdapter
from retrylab.exceptions import (
    FaultInjectionError,
    IdempotencyViolationError,
    RecoveryAssertionError,
    RetryLabError,
    ScenarioValidationError,
    SimulatedConnectionError,
    SimulatedTimeoutError,
)
from retrylab.latency import (
    LatencyDistribution,
    LatencyProfile,
)
from retrylab.models import (
    FaultScenario,
    FaultType,
    RecordedRequest,
)
from retrylab.transport import (
    AsyncRetryLabTransport,
    RetryLabTransport,
)

__version__ = "0.1.0-alpha.1"

__all__ = [
    "__version__",
    # Models
    "FaultScenario",
    "FaultType",
    "RecordedRequest",
    # Latency
    "LatencyProfile",
    "LatencyDistribution",
    # Transports & Adapters
    "RetryLabTransport",
    "AsyncRetryLabTransport",
    "RetryLabAdapter",
    # Exceptions
    "RetryLabError",
    "ScenarioValidationError",
    "FaultInjectionError",
    "SimulatedTimeoutError",
    "SimulatedConnectionError",
    "RecoveryAssertionError",
    "IdempotencyViolationError",
]
