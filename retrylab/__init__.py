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
from retrylab.patterns import (
    CircuitBreakerAuditor,
    CircuitBreakerViolation,
    CircuitBreakerViolationType,
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
from retrylab.proxy import (
    RetryLabProxyHandler,
    create_proxy_server,
    start_background_proxy,
)
from retrylab.recorder import (
    RecordedInteraction,
    ReplayTransport,
    TrafficRecorder,
)
from retrylab.reporting import (
    ReliabilityReport,
    generate_reliability_report,
)
from retrylab.scenarios import (
    ScenarioStep,
    SequentialScenario,
    StepKind,
    load_scenario_from_yaml,
    load_scenarios_from_dir,
)
from retrylab.security import DataRedactor
from retrylab.webhooks import (
    ChaosWebhookConfig,
    ChaosWebhookDispatcher,
    DispatchedWebhookResult,
    ForwardingResult,
    ForwardingRule,
    MockWebhookReceiver,
    ReceivedWebhookEvent,
    WebhookAuditReport,
    WebhookCheckResult,
    WebhookChaosMode,
    WebhookEmitter,
    WebhookEvent,
    WebhookForwarder,
    WebhookReceiverAuditor,
    WebhookReceiverFaultConfig,
    WebhookReplayEngine,
    WebhookSignatureScheme,
    compute_webhook_signature,
    verify_webhook_signature,
)
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
    # Patterns & Circuit Breakers
    "CircuitBreakerAuditor",
    "CircuitBreakerViolation",
    "CircuitBreakerViolationType",
    # Reporting
    "ReliabilityReport",
    "generate_reliability_report",
    # Recorder & Replay
    "RecordedInteraction",
    "TrafficRecorder",
    "ReplayTransport",
    # Webhooks
    "WebhookEmitter",
    "WebhookEvent",
    "WebhookSignatureScheme",
    "compute_webhook_signature",
    "verify_webhook_signature",
    "ChaosWebhookDispatcher",
    "WebhookChaosMode",
    "ChaosWebhookConfig",
    "DispatchedWebhookResult",
    "WebhookReceiverAuditor",
    "WebhookCheckResult",
    "WebhookAuditReport",
    "MockWebhookReceiver",
    "ReceivedWebhookEvent",
    "WebhookReceiverFaultConfig",
    "ForwardingRule",
    "ForwardingResult",
    "WebhookForwarder",
    "WebhookReplayEngine",
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
