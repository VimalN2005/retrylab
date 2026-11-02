"""
RetryLab: Deterministic Third-Party API Failure Simulation & Resilience Testing Engine.
"""

from retrylab.adapters.requests_adapter import RetryLabAdapter
from retrylab.assertions import (
    BackoffAuditor,
    BackoffViolation,
    BackoffViolationType,
)
from retrylab.context import simulate_fault
from retrylab.drift import (
    DriftType,
    DriftViolation,
    SchemaDriftDetector,
    SchemaDriftError,
)
from retrylab.exceptions import (
    FaultInjectionError,
    IdempotencyViolationError,
    RecoveryAssertionError,
    RetryLabError,
    ScenarioValidationError,
    SimulatedConnectionError,
    SimulatedTimeoutError,
)
from retrylab.idempotency import (
    IdempotencyAuditor,
    IdempotencyViolation,
    IdempotencyViolationType,
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
from retrylab.scenarios import (
    ScenarioStep,
    SequentialScenario,
    StepKind,
    load_scenario_from_yaml,
    load_scenarios_from_dir,
)
from retrylab.security import DataRedactor
from retrylab.transport import (
    AsyncRetryLabTransport,
    RetryLabTransport,
)

__version__ = "0.1.0-alpha.1"

__all__ = [
    "__version__",
    # Models & Scenarios
    "FaultScenario",
    "FaultType",
    "RecordedRequest",
    "SequentialScenario",
    "ScenarioStep",
    "StepKind",
    "load_scenario_from_yaml",
    "load_scenarios_from_dir",
    # Latency
    "LatencyProfile",
    "LatencyDistribution",
    # Idempotency
    "IdempotencyAuditor",
    "IdempotencyViolation",
    "IdempotencyViolationType",
    # Security & Redaction
    "DataRedactor",
    # Assertions & Budgets
    "BackoffAuditor",
    "BackoffViolation",
    "BackoffViolationType",
    # Schema Drift
    "SchemaDriftDetector",
    "SchemaDriftError",
    "DriftType",
    "DriftViolation",
    # Transports & Adapters
    "RetryLabTransport",
    "AsyncRetryLabTransport",
    "RetryLabAdapter",
    "simulate_fault",
    # Exceptions
    "RetryLabError",
    "ScenarioValidationError",
    "FaultInjectionError",
    "SimulatedTimeoutError",
    "SimulatedConnectionError",
    "RecoveryAssertionError",
    "IdempotencyViolationError",
]
