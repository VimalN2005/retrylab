# 📋 Changelog

All notable changes to the **RetryLab** project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.3.0-alpha.1] - 2026-11-21

### 🚀 Week 3 Grand Release: Developer Experience, Visual Chaos Studio, PR Commenter, Benchmarks & gRPC

This major milestone completes Phase 3 of the 30-day November sprint, introducing an interactive terminal TUI dashboard, an in-browser zero-dependency visual Chaos Studio, dark-mode SVG scorecard badges, automated GitHub Actions PR reviewing, low-level DNS/TLS failure simulation, a unified polyglot benchmark suite, and gRPC status code chaos injection.

### Added
- **Interactive Terminal TUI Dashboard & Reliability Scorecard (Day 15):**
  - `retrylab dashboard`: Full-terminal multi-panel layout rendering real-time service waterfalls, failure counters, and latency percentiles with fallback ASCII support on Windows legacy consoles.
  - `retrylab scorecard`: Automated letter-grade evaluation ($A^+$ to $F$, 0–100 score) across 5 weighted reliability dimensions: Fault Recovery (30%), Cryptographic Idempotency (25%), Exponential Backoff (20%), Circuit Breaking (15%), and Latency Overhead (10%). Supports `--format table|json|markdown`.
  - `retrylab play <scenario.yaml>`: Step-through interactive scenario execution with live terminal countdowns.
- **Chaos Studio Web Playground (Day 16):**
  - `retrylab studio`: Zero-dependency, local-first browser SPA running on `http://127.0.0.1:8400` powered by Python's built-in `http.server`.
  - Interactive scenario builder with real-time URL matching, HTTP status dropouts, and socket termination toggles.
  - Curated industry presets for Stripe payment timeouts, OpenAI 429 rate limits, and Twilio 503 carrier overloads.
  - In-flight request waterfall timeline showing attempt counts, durations, status codes, and SHA-256 idempotency verification.
  - Instant polyglot code exporter for Python (HTTPX), Go (`http.RoundTripper`), TypeScript (Fetch/Axios), and YAML.
- **Automated GitHub Actions PR Commenter & Dark-Mode SVG Visual Cards (Day 17):**
  - `generate_scorecard_svg`: High-resolution dark-mode vector scorecard badge with letter grade pills, glowing neon accents, and dimension meters.
  - `retrylab pr-comment`: Automated CI PR reviewer outputting formatted Markdown reports with embedded SVG scorecard graphics.
  - `--fail-under <score>` flag for enforcing quality gates and failing CI runs when reliability drops below thresholds.
  - Official reusable GitHub Actions workflow: `.github/workflows/pr-commenter.yml`.
- **Network-Layer Chaos Engine: DNS & SSL/TLS Certificate Faults (Day 18):**
  - Lower-level network failure simulation: `dns_failure` (`socket.gaierror`), `dns_timeout` (`socket.timeout`), `tls_handshake_timeout`, `ssl_cert_verification_failed` (`ssl.SSLCertVerificationError`), and `ssl_hostname_mismatch` (`ssl.CertificateError`).
  - Native exception chaining preserving cause objects for realistic client error handling.
  - CLI: `retrylab network simulate --fault <fault> --url <url>`.
- **Polyglot SDK Benchmark Suite & Latency Analysis (Day 19):**
  - `retrylab bench --lang all --iterations 1000`: Cross-SDK latency and throughput benchmark runner with percentiles ($P_{50}$, $P_{90}$, $P_{95}$, $P_{99}$), memory tracing, and machine-readable JSON export.
  - Verified sub-millisecond overhead: **540 nanoseconds in Go**, **3.5 microseconds in TypeScript**, and **42.3 microseconds in Python**.
  - Documented architectural comparison against Toxiproxy (Shopify) and WireMock demonstrating 100x to 3,500x lower latency.
- **gRPC & Protobuf Chaos Simulation Alpha (Day 20):**
  - Canonical gRPC status code injection (0–16): `UNAVAILABLE`, `DEADLINE_EXCEEDED`, `RESOURCE_EXHAUSTED`, `INTERNAL`, `FAILED_PRECONDITION`, etc.
  - `RetryLabUnaryClientInterceptor`: Unary-unary client interceptor for standard `grpc.Channel` (`grpc.intercept_channel`).
  - Contextual diagnostic recommendations for gRPC retry policies and per-call deadline tuning.
  - CLI: `retrylab grpc simulate --method <method> --status <status>`.
  - Polyglot gRPC code snippet generators in `PolyglotChaosMatrix` for Python, Go, and TypeScript.

### Verified
- **196 passing Python unit & integration tests** in 4.19s.
- **8 passing TypeScript unit tests** in 270ms.
- **7 passing Go unit tests** in 3.3s.
- **Total: 211 verified tests** across all 3 programming languages.

---

## [0.2.0-alpha.1] - 2026-11-14

### 🚀 Week 2 Grand Release: Advanced Chaos, Inbound Webhooks, Streaming SSE & Cross-Language SDKs

This major milestone completes Phase 2 of the 30-day November sprint, expanding RetryLab beyond outbound HTTP into inbound webhook security auditing, Server-Sent Events (SSE) AI stream disruption, low-level socket chaos, and native cross-language SDKs for Go and TypeScript.

### Added
- **Inbound Webhook Resilience & Chaos Engine:**
  - `WebhookEmitter`: Cryptographically signed webhook event dispatcher supporting `stripe_v1` (`t={ts},v1={hash}`), `github_sha256` (`sha256={hash}`), and `hmac_sha256`.
  - `ChaosWebhookDispatcher`: Simulates real-world distributed delivery chaos:
    - `DUPLICATE`: Tests receiver idempotency against at-least-once delivery duplicates.
    - `OUT_OF_ORDER`: Reverses/inverts event stream delivery order to verify out-of-order handling.
    - `INVALID_SIGNATURE`: Cryptographic secret tampering to test unverified payload rejection.
    - `CLOCK_SKEW`: Timestamp drift injection (past/future) to test tolerance limits and replay attack defenses.
  - `WebhookReceiverAuditor`: Automated 4-point security and resilience test battery against receiver endpoints.
  - CLI: `retrylab webhook audit` and `retrylab webhook dispatch`.
- **Mock Webhook Receiver, Forwarding Tunnel & Fixture Replay:**
  - `MockWebhookReceiver`: In-process webhook event store with configurable fault policies (`fail_first_n`, `delay_seconds`, signature verification).
  - `WebhookForwarder`: Local forwarding tunnel routing captured webhooks to developer services.
  - `WebhookReplayEngine`: Parses recorded JSON event fixtures and replays them with configurable intervals.
  - CLI: `retrylab webhook listen` (with real-time colored log stream) and `retrylab webhook replay`.
- **Server-Sent Events (SSE) & LLM Stream Disruption:**
  - `SSEEvent` and `SSEStreamParser`: Incremental parser and encoder for W3C Server-Sent Events.
  - `StreamingFaultTransport`: In-process stream chunk generation via `httpx.SyncByteStream`.
  - `ChaosStreamGenerator`: Mid-stream disruption simulator:
    - `TRUNCATE`: Simulates abrupt TCP EOF / premature stream cutoff.
    - `DROP_CHUNKS`: Simulates mid-stream packet loss and dropped tokens.
    - `CORRUPT_JSON`: Injects malformed JSON syntax into streaming chunks.
    - `MID_STREAM_STALL`: Introduces artificial stalls between chunks to test client read timeouts.
    - `INJECT_ERROR`: Injects in-band SSE error events (e.g. 503 generation crash) mid-stream.
  - AI Presets: Built-in `build_openai_chat_stream` and `build_anthropic_messages_stream`.
  - CLI: `retrylab stream simulate --preset openai --chaos truncate`.
- **Low-Level Socket & TCP Layer Chaos:**
  - `SocketFaultSimulator`: Models transport-level faults beneath HTTP:
    - `CONNECTION_RESET`: TCP RST packet / `ConnectionResetError`.
    - `SILENT_DROP`: Blackhole packet drop leading to read timeout.
    - `SLOW_DRIP`: Trickle chunk delivery (configurable bytes/sec) to test slowloris & chunk read timeouts.
    - `MALFORMED_RAW_RESPONSE`: Corrupt non-HTTP wire bytes.
    - `PREMATURE_CLOSE`: Socket closed prematurely mid-transmission.
  - `SocketChaosTransport` (HTTPX) and `SocketChaosAdapter` (Requests): Maps socket chaos to native client exceptions.
  - CLI: `retrylab socket simulate --fault connection_reset`.
- **Official Go SDK Alpha (`github.com/VimalN2005/retrylab/sdk/go`):**
  - In-process `http.RoundTripper` interceptor (`retrylab.NewTransport(scenario)`).
  - SHA-256 cryptographic idempotency auditor (`IdempotencyAuditor`) and backoff timing verifier (`BackoffAuditor`).
  - Production Stripe payment retry demo in `sdk/go/examples/stripe_resilience/`.
  - Dedicated multi-version Go GitHub Actions CI workflow (`.github/workflows/go-ci.yml`).
- **Official TypeScript & Node.js SDK Alpha (`@retrylab/retrylab`):**
  - In-process Fetch interceptor (`createRetryLabFetch`) for Node.js 18+, Bun, Deno, and Next.js.
  - In-process Axios adapter (`attachRetryLabToAxios`, `createRetryLabAxiosAdapter`).
  - SHA-256 idempotency auditor and exponential backoff verifier in TypeScript.
  - AI Agent OpenAI completion resilience demo in `sdk/ts/examples/openai-agent-resilience.ts`.
  - Dedicated multi-version Node.js GitHub Actions CI workflow (`.github/workflows/ts-ci.yml`).
- **Polyglot Chaos Matrix:**
  - `PolyglotChaosMatrix` and `PolyglotScenarioSchema`: Cross-SDK canonical scenario schema with native Go struct and TypeScript object code generators.

### Verified
- **133 passing Python unit & integration tests** running in 3.29s.
- **8 passing TypeScript unit tests** running in 159ms.
- **7 passing Go unit tests** with `-race` detection in 2.75s.
- **Total: 148 verified tests** across all 3 programming languages.

---

## [0.1.0-alpha.1] - 2026-11-03

### 🚀 Week 1 Grand Release: Core Engine Architecture & Resilience Matrix

This milestone establishes RetryLab as a zero-daemon, deterministic API reliability testing engine for Python backends, AI agents, and fintech services.

### Added
- **Multi-Client Interception Transports:**
  - `RetryLabTransport`: In-process synchronous `httpx.BaseTransport` interceptor.
  - `AsyncRetryLabTransport`: Asynchronous `httpx.AsyncBaseTransport` for modern async/await FastAPI applications.
  - `RetryLabAdapter`: Standard `requests.adapters.BaseAdapter` for standard SDKs (e.g. `boto3`, `stripe`).
- **Chaos & Fault Matrix:**
  - Deterministic simulation of `TIMEOUT`, `RATE_LIMIT_429` (with dynamic `Retry-After`), `SERVER_ERROR_500`, `BAD_GATEWAY_502`, `SERVICE_UNAVAILABLE_503`, `GATEWAY_TIMEOUT_504`, and `CONNECTION_RESET`.
- **Dynamic Latency & Network Modeling:**
  - `LatencyProfile`: Supports `FIXED`, `UNIFORM` jitter, `NORMAL` gaussian distributions, `SPIKE` modeling (random congestion simulation), and `RAMP` linear degradation.
- **Cryptographic Idempotency & Duplicate Mutation Guard:**
  - `IdempotencyAuditor`: Canonical JSON SHA-256 fingerprinting to detect duplicate charges, dropped idempotency keys, and payload mutations across retries.
- **Multi-Step Progressive Outage State Machine:**
  - `SequentialScenario`: Simulates complex progressive outages (e.g. Step 1: Timeout ➔ Step 2: 503 Service Unavailable ➔ Step 3: Recover 200 OK).
- **Declarative YAML Scenario Engine:**
  - `load_scenario_from_yaml`: Pydantic V2-validated YAML scenario loader supporting human-friendly delays (`50ms`, `0.5s`) and wildcard URL pattern matching.
  - `load_scenarios_from_dir`: Ingests entire directories of scenario definitions.
- **Pytest Plugin & Zero-Boilerplate Context Manager:**
  - `simulate_fault`: Transparently patches HTTPX and Requests client constructors within a context block.
  - Pytest fixtures: `retrylab_auditor`, `make_fault_client`, `make_fault_session`.
- **Automated PII & Secret Redaction Engine:**
  - `DataRedactor`: Automatically scrubs Bearer tokens, OpenAI keys (`sk-...`), credit cards, and sensitive JSON keys from test logs and reports.
- **API Schema Drift & Contract Breaking Change Detector:**
  - `SchemaDriftDetector`: Recursively compares candidate responses against baselines, flagging missing fields, type mutations, and nullability errors.
- **Typer Command-Line Interface (CLI):**
  - `retrylab validate`: Validates YAML scenario syntax.
  - `retrylab info`: Displays human-readable scenario breakdown.
  - `retrylab drift`: Inspects two JSON files for API contract schema drift.
  - `retrylab serve`: Launches the local HTTP forward proxy server.
  - `retrylab gate`: Runs CI quality gate with automated summary generation.
- **Exponential Backoff & Retry Budget Auditor:**
  - `BackoffAuditor`: Flags busy-loop retry spamming, verifies exponential interval progression, and enforces maximum attempt and latency budgets.
- **Cross-Language HTTP Forward Proxy Daemon:**
  - Built-in zero-dependency HTTP server allowing Go, Node.js, and curl microservices to route through RetryLab scenarios.
- **Multi-Format Reliability Reporting:**
  - `ReliabilityReport`: Generates self-contained dark-themed HTML dashboards (`report.html`), GitHub Actions Markdown summaries (`report.md`), and JSON outputs.
- **Traffic Recording & Offline Fixture Replay:**
  - `TrafficRecorder`: Sanitizes and records live HTTP traffic into reusable JSON fixtures.
  - `ReplayTransport`: Replays recorded fixtures offline with optional fault injection.
- **Circuit Breaker & Fail-Fast Pattern Auditor:**
  - `CircuitBreakerAuditor`: Asserts that clients trip their circuit breaker OPEN after consecutive failures rather than hammering upstream dependencies.
- **Official GitHub Action CI Gate:**
  - Reusable composite GitHub Action in `.github/actions/retrylab-action/action.yml` for pull request step summaries.
- **FastAPI AI Agent Production Demo:**
  - Production-grade AI Agent service with automated chaos test suite in `examples/ai_agent_service/`.
- **Performance Benchmark Suite:**
  - Sub-millisecond pass-through verification (0.045ms overhead, 17,000+ RPS) in `benchmarks/`.

### Verified
- **70 passing unit & integration tests** running in 1.25s.
