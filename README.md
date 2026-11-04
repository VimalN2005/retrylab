<div align="center">

# 🧪 RetryLab

### **Test failures. Verify recovery. Ship with confidence.**

*A local-first, zero-daemon API reliability testing and chaos engineering toolkit for Python applications.*

[![CI](https://github.com/VimalN2005/retrylab/actions/workflows/ci.yml/badge.svg)](https://github.com/VimalN2005/retrylab/actions)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-114%20passed-brightgreen.svg)](https://github.com/VimalN2005/retrylab)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

Simulate external API failures, test retry behaviour, and verify that your application recovers correctly — before those failures reach production.

[Quickstart](#-quickstart) • [Why RetryLab?](#-the-problem) • [Architecture](#-how-it-works) • [Demo](#-terminal-demo) • [Roadmap](#-roadmap-november-2026-sprint)

</div>

---

> [!NOTE]
> **Active Sprint in Progress:** RetryLab is an early-stage, local-first open-source developer tool. Core HTTPX transports, Requests adapters, dynamic latency models, and cryptographic idempotency auditing are already functional and unit-tested. Declarative YAML scenario runners and Pytest plugin extensions are actively rolling out.

---

## ⚡ The Problem

Modern backend and AI applications depend almost entirely on external third-party services:
- **AI APIs:** OpenAI, Anthropic, Cohere, and Hugging Face.
- **Payment Gateways:** Stripe, Adyen, Razorpay, and Plaid.
- **Messaging & Notifications:** Twilio, SendGrid, Resend, and Slack.
- **Cloud Infrastructure & SaaS:** AWS, GitHub, Supabase, and Redis Cloud.

In development and staging, these services almost always return `HTTP 200 OK`. But in production:
1. **OpenAI suddenly throws `HTTP 429 (Too Many Requests)`:** Does your application use exponential backoff with jitter, or does it trigger an unintended retry DDoS loop?
2. **Stripe drops connection halfway through a transaction:** Does your application retry with the exact same `Idempotency-Key`, or does it double-charge the customer?
3. **Twilio experiences a 15-second latency spike:** Does your worker thread pool starve and cascade into a complete service outage?
4. **Upstream payload mutation:** Does your retried request accidentally alter the payload body, causing downstream payment gateways to reject it with `HTTP 400`?

**Happy-path integration testing cannot reliably catch these failure modes.** Standard mocks (`unittest.mock`, `responses`) only return static responses and cannot verify dynamic recovery paths, idempotency guarantees, or backoff policies.

---

## 💡 What is RetryLab?

**RetryLab** is a developer-first testing engine that makes external dependency failure predictable, repeatable, and easily testable on your local machine and in CI pipelines.

Instead of waiting for an outage in production, developers configure deterministic failure scenarios (e.g., *"fail attempt 1 with a timeout, then recover on attempt 2"*) and verify whether their application survives and recovers cleanly.

---

## 🖥️ Terminal Demo

Here is RetryLab running an automated recovery and idempotency audit on a simulated Stripe checkout:

```text
==================================== RETRYLAB TEST RUN ====================================
[Scenario] Target: https://api.stripe.com/v1/charges | Fault: TIMEOUT | Failures: 1

--> Attempt #1: POST https://api.stripe.com/v1/charges
    [FAULT INJECTED] Simulated ReadTimeout (delay: 0.15s)
    [CLIENT LOG] Payment timed out! Triggering backoff retry...

--> Attempt #2: POST https://api.stripe.com/v1/charges
    [RECOVERED] Status: 200 OK | Response: {"status": "charge_confirmed"}
    [CLIENT LOG] Transaction confirmed on retry!

--------------------------------- RELIABILITY AUDIT ---------------------------------
[*] Total Outbound Requests: 2
[*] Injected Faults:         1 (Attempt #1)
[*] Recovery Status:         PASS (Clean recovery on Attempt #2)
[*] Idempotency Audit:       PASS (Same Idempotency-Key preserved: 'safe_order_tx_98765')
[*] Payload Integrity:       PASS (SHA-256 fingerprint matching across retries)
================================ 1 SCENARIO PASSED in 0.22s ================================
```

---

## 🎯 Key Features & Capabilities

| Capability | Status | Description |
| :--- | :---: | :--- |
| **HTTPX Sync Interception** | ✅ Ready | Custom `httpx.BaseTransport` for in-process sync client interception. |
| **HTTPX Async Interception** | ✅ Ready | `httpx.AsyncBaseTransport` for modern async/await FastAPI applications. |
| **Requests Adapter** | ✅ Ready | `requests.adapters.BaseAdapter` (`RetryLabAdapter`) for standard SDKs (e.g. `boto3`, `stripe`). |
| **Fault Matrix (429, 500, 503)** | ✅ Ready | Realistic status code generation with dynamic `Retry-After` headers. |
| **Timeout & Socket Resets** | ✅ Ready | Emulate `ReadTimeout`, `ConnectTimeout`, and sudden TCP disconnects. |
| **Dynamic Latency Engine** | ✅ Ready | Realistic network profiles: `FIXED`, `UNIFORM` jitter, `NORMAL` gaussian, and `SPIKE` models. |
| **Idempotency Auditor** | ✅ Ready | SHA-256 canonical JSON hashing to detect duplicate payments and payload mutations. |
| **Pytest Declarative Fixture** | ✅ Ready | `@pytest.mark.retrylab(...)` and `simulate_fault` fixtures for zero-boilerplate testing. |
| **YAML Scenario Runner** | ✅ Ready | Declarative YAML scenario parser (`load_scenario_from_yaml`) for cross-language teams. |
| **Multi-Step State Machine** | ✅ Ready | Progressive multi-step outages (`SequentialScenario`: Timeout ➔ 503 ➔ 200). |
| **Typer CLI Runner** | ✅ Ready | `retrylab validate`, `retrylab info`, and `retrylab drift` commands. |
| **Schema Drift Detector** | ✅ Ready | Detects breaking API contract changes (missing fields, unexpected types/nulls). |
| **Data Redaction & Security** | ✅ Ready | Automated scrubbing of Bearer tokens, OpenAI keys, and CVVs from test logs. |
| **HTTP Proxy Daemon** | ✅ Ready | `retrylab serve` local proxy server for cross-language testing (Go, Node.js, curl). |
| **Reliability Reports (HTML & MD)** | ✅ Ready | Beautiful self-contained dark HTML dashboards & GitHub PR Markdown summaries. |
| **Exponential Backoff Verifier** | ✅ Ready | Audits retry intervals, budget limits, and detects aggressive zero-delay spam. |
| **Traffic Recorder & Offline Replay** | ✅ Ready | Captures sanitized live requests and replays offline fixtures with fault injection. |
| **Circuit Breaker Auditor** | ✅ Ready | Verifies client fail-fast behavior and prevents cascading thundering herds. |
| **GitHub Actions CI Quality Gate** | ✅ Ready | Official GitHub Action & `retrylab gate` command for PR step summaries. |
| **Webhook Resilience & Chaos Engine** | ✅ Ready | HMAC signature forging, duplicate delivery, clock skew, and receiver audit CLI. |
| **Webhook Mock Receiver & Forwarding** | ✅ Ready | Local event inspector, forwarding tunnel (`retrylab webhook listen`), and offline fixture replay. |
| **SSE & LLM Streaming Disruption** | ✅ Ready | Mid-stream truncation, token dropouts, malformed JSON, stalls, and OpenAI/Anthropic presets. |

---

## 🏗️ How It Works

RetryLab intercepts outbound HTTP traffic directly at the transport boundary before it reaches the network socket. No heavy Docker daemons, local proxies, or DNS hijacking required:

```mermaid
flowchart TD
    App["Your Application / Service Logic"] --> Client["HTTP Client (HTTPX / Requests)"]
    Client --> Transport["RetryLab Transport / Adapter"]
    
    subgraph RetryLab Engine
        Transport --> Matcher{"URL Pattern Matcher"}
        Matcher -- "Match" --> StateMachine["Scenario State Machine"]
        Matcher -- "Unmatched" --> Passthrough["Pass-Through / Real Network"]
        
        StateMachine --> Attempts{"Attempts < Fail Count?"}
        Attempts -- "Yes (Inject)" --> FaultEngine["Fault Injection Engine"]
        FaultEngine --> Chaos["Timeout / 429 / 500 / Latency"]
        
        Attempts -- "No (Recover)" --> RecoveryEngine["Recovered Response (200 OK)"]
    end
    
    Chaos --> App
    RecoveryEngine --> App
    
    App --> Auditor["Idempotency & Recovery Auditor"]
    Auditor --> Report["Assertion Report (CI / Pytest)"]
```

---

## 🚀 Quickstart

### 1. Installation

```bash
pip install retrylab
```

### 2. Testing OpenAI Rate-Limit Recovery (`HTTPX`)

```python
import httpx
from retrylab import FaultScenario, FaultType, RetryLabTransport

# Scenario: OpenAI returns 429 on attempt 1, then recovers on attempt 2
scenario = FaultScenario(
    target="https://api.openai.com/v1/*",
    fault=FaultType.RATE_LIMIT_429,
    retry_after_seconds=2,
    fail_count=1,
)

transport = RetryLabTransport(scenario=scenario)

with httpx.Client(transport=transport) as client:
    # Attempt 1 -> 429 Rate Limit (Header: Retry-After: 2)
    resp1 = client.post("https://api.openai.com/v1/chat/completions", json={"model": "gpt-4o"})
    assert resp1.status_code == 429
    
    # Attempt 2 -> 200 OK (Application recovers after respecting backoff)
    resp2 = client.post("https://api.openai.com/v1/chat/completions", json={"model": "gpt-4o"})
    assert resp2.status_code == 200
```

### 3. Auditing Stripe Payment Idempotency (`Requests` or `HTTPX`)

```python
from retrylab import FaultScenario, FaultType, IdempotencyAuditor, RetryLabTransport

scenario = FaultScenario(
    target="https://api.stripe.com/v1/charges",
    fault=FaultType.TIMEOUT,
    fail_count=1,
)
auditor = IdempotencyAuditor(idempotency_header="Idempotency-Key")

# Run your payment code with RetryLab transport attached...
# If your application changes the idempotency key or alters the payload body on retry:
auditor.assert_idempotent(scenario)
# Raises IdempotencyViolationError if any double-charge or mutation risk is found!
```

---

## 📄 Declarative YAML Scenario Preview (Planned)

Define scenarios once and run them anywhere:

```yaml
version: 1
name: payment_resilience_test
match:
  method: POST
  url: "https://api.stripe.com/v1/charges"
steps:
  - kind: fault
    type: timeout
    delay: 0.2s
  - kind: fault
    type: http_status
    code: 503
    retry_after: 2
  - kind: recover
    code: 200
    body:
      status: "succeeded"
      charge_id: "ch_987654321"
assertions:
  max_retries: 3
  enforce_idempotency: true
  idempotency_header: "Idempotency-Key"
```

### 5. Webhook Ingestion & Resilience Audit

Test your incoming webhook endpoint against duplicate deliveries, forged HMAC signatures, and expired timestamps:

```bash
# Run security & idempotency audit on your local webhook endpoint
retrylab webhook audit http://localhost:8000/api/v1/webhooks/stripe --secret "whsec_test" --scheme stripe_v1

# Dispatch duplicate synthetic events to test idempotent at-least-once ingestion
retrylab webhook dispatch http://localhost:8000/api/v1/webhooks/stripe --secret "whsec_test" --chaos duplicate --duplicates 3

# Start a local mock webhook listener with fault injection (fail first 2 attempts with HTTP 500)
retrylab webhook listen --port 8085 --secret "whsec_test" --fail-first 2 --fail-status 500 --forward-to http://localhost:8000/api/webhook

# Replay recorded webhook event fixtures against an endpoint
retrylab webhook replay fixtures/stripe_webhooks.json --target http://localhost:8000/api/webhook
```

### 6. AI Agent & LLM Stream Disruption

Simulate mid-stream network dropouts and corrupted token deltas against OpenAI or Anthropic streaming endpoints:

```bash
# Simulate premature stream truncation (disconnect after 4 tokens)
retrylab stream simulate --preset openai --chaos truncate --truncate-after 4

# Simulate mid-stream API 503 generation crash
retrylab stream simulate --preset anthropic --chaos inject_error
```

---

## 📐 Design Principles

- 🏠 **Local-First:** Core tests run 100% in-process on your developer machine without spinning up external servers or Docker containers.
- 🎲 **Deterministic:** The exact same scenario config generates the exact same sequence of failures every single time.
- 🛡️ **Safe by Default:** Never sends unintended external network calls during testing.
- 🔒 **Privacy-Conscious:** Sensitive headers (Bearer tokens, Authorization, CVV) are automatically redacted in audit reports.
- ⚡ **CI-Ready:** Seamlessly runs inside GitHub Actions, GitLab CI, or CircleCI with zero configuration overhead.

---

## 🗺️ Roadmap (November 2026 Sprint)

| Phase | Timeline | Focus | Status |
| :--- | :--- | :--- | :---: |
| **Phase 1: Foundation & Core Matrix** | Nov 1 – Nov 7 | Sync/Async HTTPX Transports, Requests Adapter, Dynamic Latency, Cryptographic Idempotency, YAML Scenarios, Pytest Plugin, Security Redactor, Schema Drift, HTTP Proxy, Reports, Fixture Replay, CI Gate | **✅ COMPLETED (100%)** |
| **Phase 2: Advanced Chaos & Webhooks** | Nov 8 – Nov 14 | Webhook failure emulation, async stream disruption, TCP socket cutoffs, dynamic chaos scheduling | ⚡ **In Progress (Days 8, 9 & 10 Complete)** |
| **Phase 3: DX & Multi-Language SDKs** | Nov 15 – Nov 21 | Go SDK alpha, Node.js SDK alpha, enhanced PR scorecard generator | Planned |
| **Phase 4: Launch & Ecosystem** | Nov 22 – Nov 30 | Production PyPI release, live developer playground, interactive demo video | Planned |

---

## 🏎️ Performance Benchmarks

RetryLab is engineered for extreme efficiency with **zero-daemon in-process transport interception**:

| Benchmark | Latency Per Request | Throughput | Overhead |
| :--- | :---: | :---: | :---: |
| **Raw Baseline HTTPX** | `13.98 µs` | 71,500 req/sec | Baseline |
| **RetryLab Interceptor** | `58.67 µs` | **17,044 req/sec** | **+0.045 ms** |

*Measured across 1,000 continuous requests. See [benchmarks/RESULTS.md](benchmarks/RESULTS.md) for full benchmark methodology.*

---

## 🤝 Contributing

Contributions from the developer community are warmly welcomed! Whether it is adding new fault models, improving documentation, or adding client adapters:

1. Fork the repository.
2. Create your feature branch (`git checkout -b feat/amazing-fault-model`).
3. Ensure all tests pass (`pytest -v`).
4. Commit your changes (`git commit -m "feat: add new fault model"`).
5. Push to the branch and open a Pull Request.

---

## 🔐 Security & Responsible Testing

RetryLab is intended exclusively for local and CI resilience testing in staging/test environments.
- **Do not** hardcode production API credentials, real card tokens, or customer PII in scenario files.
- To report a security concern, please contact [vimaln2005@users.noreply.github.com](mailto:vimaln2005@users.noreply.github.com) privately.

---

## 📜 License

Distributed under the **MIT License**. See [LICENSE](LICENSE) for more details.

<div align="center">

**RetryLab** — *Don't just test success. Test recovery.*

</div>
