"""
RetryLab: Deterministic Third-Party API Failure Simulation & Resilience Testing Engine.
"""

__version__ = "0.3.0-alpha.1"

from retrylab.adapters.requests_adapter import RetryLabAdapter
from retrylab.assertions import (
    BackoffAuditor,
    BackoffViolation,
    BackoffViolationType,
)
from retrylab.benchmark import (
    BenchmarkReport,
    LatencyMetrics,
    PythonBenchmarkRunner,
    render_benchmark_table,
    run_polyglot_benchmark,
)
from retrylab.context import simulate_fault
from retrylab.doctor import (
    DiagnosticCheck,
    DoctorReport,
    RetryLabDoctor,
)
from retrylab.soak import (
    RequestSample,
    SoakConfig,
    SoakFaultMode,
    SoakResult,
    calculate_storm_severity,
    render_soak_table,
    run_soak_test,
)
from retrylab.tour import (
    RetryLabTour,
    TourLessonResult,
    TourStep,
    get_all_tour_steps,
    get_tour_step_by_number,
    render_completion_summary,
)
from retrylab.drift import (
    DriftType,
    DriftViolation,
    SchemaDriftDetector,
    SchemaDriftError,
)
from retrylab.grpc import (
    GRPCFaultConfig,
    GRPCRecordedCall,
    GRPCStatusCode,
    RetryLabUnaryClientInterceptor,
    SimulatedGRPCError,
    create_intercepted_channel,
    get_grpc_recommendation,
    to_grpc_status,
)
from retrylab.exceptions import (
    FaultInjectionError,
    IdempotencyViolationError,
    RecoveryAssertionError,
    RetryLabError,
    ScenarioValidationError,
    SimulatedConnectionError,
    SimulatedDNSError,
    SimulatedSSLError,
    SimulatedTLSHandshakeTimeout,
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
from retrylab.matrix import (
    PolyglotChaosMatrix,
    PolyglotScenarioSchema,
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
    generate_pr_comment,
    generate_reliability_report,
    generate_scorecard_svg,
)
from retrylab.tui import (
    EndpointResilienceEntry,
    InteractiveScenarioRunner,
    MetricScore,
    ReliabilityScorecard,
    ScorecardEvaluator,
    ScorecardGrade,
    display_dashboard,
    render_dashboard_layout,
)
from retrylab.studio import (
    ChaosStudioHandler,
    ChaosStudioPreset,
    ChaosStudioServer,
    create_studio_server,
    get_all_presets,
    get_preset_by_id,
    start_background_studio,
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
from retrylab.streaming import (
    ChaosStreamGenerator,
    SSEEvent,
    SSEStreamParser,
    StreamingByteIterator,
    StreamingChaosConfig,
    StreamingChaosMode,
    StreamingFaultTransport,
    build_anthropic_messages_stream,
    build_openai_chat_stream,
    create_streaming_fault_transport,
)
from retrylab.socket import (
    SocketChaosAdapter,
    SocketChaosConfig,
    SocketChaosTransport,
    SocketFaultSimulator,
    SocketFaultType,
)
from retrylab.transport import (
    AsyncRetryLabTransport,
    RetryLabTransport,
)

__all__ = [
    "__version__",
    # Models & Scenarios
    "FaultScenario",
    "FaultType",
    "PolyglotScenarioSchema",
    "PolyglotChaosMatrix",
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
    "generate_scorecard_svg",
    "generate_pr_comment",
    # TUI & Scorecard
    "EndpointResilienceEntry",
    "InteractiveScenarioRunner",
    "MetricScore",
    "ReliabilityScorecard",
    "ScorecardEvaluator",
    "ScorecardGrade",
    "display_dashboard",
    "render_dashboard_layout",
    # Chaos Studio
    "ChaosStudioPreset",
    "get_all_presets",
    "get_preset_by_id",
    "ChaosStudioHandler",
    "ChaosStudioServer",
    "create_studio_server",
    "start_background_studio",
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
    # Streaming & SSE
    "SSEEvent",
    "SSEStreamParser",
    "StreamingByteIterator",
    "StreamingFaultTransport",
    "ChaosStreamGenerator",
    "StreamingChaosConfig",
    "StreamingChaosMode",
    "build_openai_chat_stream",
    "build_anthropic_messages_stream",
    "create_streaming_fault_transport",
    # Socket & TCP Chaos
    "SocketChaosConfig",
    "SocketFaultSimulator",
    "SocketFaultType",
    "SocketChaosTransport",
    "SocketChaosAdapter",
    # Benchmarking
    "BenchmarkReport",
    "LatencyMetrics",
    "PythonBenchmarkRunner",
    "render_benchmark_table",
    "run_polyglot_benchmark",
    # gRPC & Protobuf Chaos
    "GRPCStatusCode",
    "GRPCFaultConfig",
    "GRPCRecordedCall",
    "RetryLabUnaryClientInterceptor",
    "SimulatedGRPCError",
    "create_intercepted_channel",
    "get_grpc_recommendation",
    "to_grpc_status",
    # Diagnostic Doctor
    "DiagnosticCheck",
    "DoctorReport",
    "RetryLabDoctor",
    # Soak & Stress Testing
    "RequestSample",
    "SoakConfig",
    "SoakFaultMode",
    "SoakResult",
    "calculate_storm_severity",
    "render_soak_table",
    "run_soak_test",
    # Guided Tour
    "TourStep",
    "TourLessonResult",
    "RetryLabTour",
    "get_all_tour_steps",
    "get_tour_step_by_number",
    "render_completion_summary",
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
    "SimulatedDNSError",
    "SimulatedSSLError",
    "SimulatedTLSHandshakeTimeout",
    "RecoveryAssertionError",
    "IdempotencyViolationError",
]
