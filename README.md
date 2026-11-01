<div align="center">

# 🧪 RetryLab

**Deterministic Third-Party API Failure Simulation & Resilience Testing Engine**

[![CI](https://github.com/VimalN2005/retrylab/actions/workflows/ci.yml/badge.svg)](https://github.com/VimalN2005/retrylab/actions)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

*Don't just test if your integration works. Test if your application survives when dependencies fail.*

[Quickstart](#quickstart) • [Why RetryLab?](#why-retrylab) • [Architecture](#architecture) • [Roadmap](#roadmap)

</div>

---

## ⚡ The Problem

Modern backend applications depend heavily on external APIs:
- **AI startups** rely on OpenAI, Anthropic, or Cohere.
- **Fintech startups** rely on Stripe, Plaid, or Razorpay.
- **SaaS startups** rely on AWS, Twilio, SendGrid, and GitHub.

In staging, these third-party APIs return HTTP 200 nearly 100% of the time. But in production:
1. **OpenAI throws HTTP 429 (Rate Limit)** during traffic spikes. Does your retry mechanism introduce exponential backoff, or does it trigger a self-inflicted DDoS?
2. **Stripe drops connection halfway through a charge.** Does your service retry with the exact same `Idempotency-Key`, or does it double-charge the customer?
3. **Twilio experiences a 15-second latency spike.** Does your thread pool starve and cause an outage across your entire microservice?

Existing mock tools (`unittest.mock`, `responses`, `wiremock`) only return static canned responses. They **do not verify dynamic recovery, retry policies, or idempotency safety**.

**RetryLab solves this.**

---

## 🚀 Key Capabilities

- 🎯 **Deterministic Fault Injection:** Simulate timeouts, HTTP 429 rate limits with dynamic `Retry-After` headers, 502/503 crashes, and connection drops on specific endpoints without modifying your business logic.
- 🔁 **Recovery Verification:** Assert that your application retries failed requests within defined budgets and recovers cleanly once the upstream dependency stabilizes.
- 🛡️ **Idempotency Auditor:** Verify that retried mutations (POST/PUT/PATCH) maintain identical idempotency tokens and don't create duplicate downstream records.
- ⚡ **Zero-Daemon Python-Native Interception:** Works directly in-process via custom HTTP transports (`httpx` & `requests`). No heavy external proxies or Docker containers required for testing.
- 🧪 **Pytest-First Experience:** Run resilience tests directly inside your standard CI test suite with declarative decorators.

---

## 🏗️ Architecture

RetryLab intercepts outbound HTTP traffic directly at the transport boundary before it hits the network socket:

```
┌────────────────────────────────────────────────────────┐
│             Your Application / Service Logic           │
└────────────────────────────────────────────────────────┘
                            │
               (httpx.Client / AsyncClient)
                            ▼
┌────────────────────────────────────────────────────────┐
│                   RetryLab Transport                   │
│                                                        │
│  ┌───────────────────┐        ┌─────────────────────┐  │
│  │ Pattern Matcher   │───────►│ Scenario Controller │  │
│  └───────────────────┘        └─────────────────────┘  │
│                                          │             │
│                       ┌──────────────────┴──────────┐  │
│                       ▼                             ▼  │
│             [Injected Fault State]        [Healthy State]
│             - Timeout                      - Passthrough
│             - HTTP 429 / 503               - Recorded Mock
│             - Socket Reset                             │
└────────────────────────────────────────────────────────┘
```

---

## 📦 Quickstart (Preview)

### Installation

```bash
pip install retrylab
```

### Basic Usage with HTTPX

```python
import httpx
from retrylab import FaultScenario, FaultType, RetryLabTransport

# Define a deterministic failure scenario: 1 timeout, then healthy
scenario = FaultScenario(
    target="https://api.openai.com/v1/*",
    fault=FaultType.TIMEOUT,
    fail_count=1,
)

# Attach RetryLab transport
transport = RetryLabTransport(scenario=scenario)

with httpx.Client(transport=transport) as client:
    # First attempt: Simulates ReadTimeout
    # Second attempt: Passes through or recovers
    ...
```

---

## 🗺️ Roadmap (November 2026 Sprint)

- [x] **Week 1 (Nov 1 - Nov 7):** Core Engine Architecture, Sync/Async HTTPX Transport Interception, Pydantic V2 Models.
- [ ] **Week 2 (Nov 8 - Nov 14):** Chaos Matrix: Timeouts, 429 Rate-Limits, 502/503 Crashes, Dynamic Latency Injection.
- [ ] **Week 3 (Nov 15 - Nov 21):** Recovery Assertions, Idempotency Validator, Pytest Plugin (`pytest-retrylab`).
- [ ] **Week 4 (Nov 22 - Nov 30):** Stripe & OpenAI Integration Demos, CLI Runner, Official PyPI Release.

---

## 🤝 Contributing

Contributions are welcome! Please check out [CONTRIBUTING.md](CONTRIBUTING.md) to get started.

## 📄 License

Distributed under the MIT License. See [LICENSE](LICENSE) for more information.
