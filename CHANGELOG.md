# 📋 Changelog

All notable changes to the **RetryLab** project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
