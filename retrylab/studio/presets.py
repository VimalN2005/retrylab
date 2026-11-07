"""
Built-in Chaos Studio Presets Catalog.
Provides curated industry resilience templates for Fintech, AI agents, SaaS, and Cloud APIs.
"""

from __future__ import annotations

from typing import Any, List, Optional
from pydantic import BaseModel, Field


class ChaosStudioPreset(BaseModel):
    """Template configuration for a pre-configured chaos scenario."""

    id: str
    name: str
    category: str
    description: str
    target: str
    method: str = "POST"
    fault: str = "http_status"  # http_status, timeout, disconnect
    fail_count: int = 1
    status_code: int = 503
    delay_ms: int = 50
    recover_status: int = 200
    idempotency_header: str = "Idempotency-Key"
    tags: List[str] = Field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert preset to dictionary."""
        return self.model_dump()


STUDIO_PRESETS: List[ChaosStudioPreset] = [
    ChaosStudioPreset(
        id="stripe_payment_timeout",
        name="Stripe ReadTimeout & Idempotent Recovery",
        category="Fintech & Payments",
        description="Simulates a payment gateway socket timeout on attempt 1. Verifies that the client preserves the Idempotency-Key across retries without double-charging.",
        target="https://api.stripe.com/v1/charges",
        method="POST",
        fault="timeout",
        fail_count=1,
        status_code=504,
        delay_ms=120,
        recover_status=200,
        idempotency_header="Idempotency-Key",
        tags=["stripe", "fintech", "idempotency", "timeout"],
    ),
    ChaosStudioPreset(
        id="openai_rate_limit_429",
        name="OpenAI HTTP 429 Rate Limit Backoff",
        category="AI & LLM Services",
        description="Simulates token quota exhaustion with HTTP 429 Too Many Requests. Verifies exponential backoff with jitter before recovery on attempt 3.",
        target="https://api.openai.com/v1/chat/completions",
        method="POST",
        fault="http_status",
        fail_count=2,
        status_code=429,
        delay_ms=60,
        recover_status=200,
        idempotency_header="Idempotency-Key",
        tags=["openai", "llm", "rate-limit", "backoff"],
    ),
    ChaosStudioPreset(
        id="twilio_sms_service_unavailable",
        name="Twilio SMS 503 Carrier Gateway Overload",
        category="Messaging & Notifications",
        description="Simulates upstream telecom gateway congestion returning HTTP 503. Tests client retry queue and backoff compliance.",
        target="https://api.twilio.com/2010-04-01/Accounts/*/Messages",
        method="POST",
        fault="http_status",
        fail_count=1,
        status_code=503,
        delay_ms=80,
        recover_status=200,
        idempotency_header="Idempotency-Key",
        tags=["twilio", "sms", "carrier", "503"],
    ),
    ChaosStudioPreset(
        id="tcp_socket_connection_reset",
        name="Service Mesh TCP Connection Reset (RST)",
        category="Networking & Mesh",
        description="Simulates sudden socket termination by an intermediate proxy or Envoy sidecar. Verifies that the HTTP client catches socket resets and recovers cleanly.",
        target="https://internal.service.mesh/v1/data",
        method="GET",
        fault="disconnect",
        fail_count=1,
        status_code=502,
        delay_ms=10,
        recover_status=200,
        idempotency_header="Idempotency-Key",
        tags=["tcp", "socket", "reset", "mesh"],
    ),
    ChaosStudioPreset(
        id="github_rate_limit_secondary",
        name="GitHub REST API Secondary Rate Limit (403)",
        category="DevOps & Cloud",
        description="Simulates GitHub secondary rate limiting when querying repositories concurrently in CI workflows.",
        target="https://api.github.com/repos/*",
        method="GET",
        fault="http_status",
        fail_count=1,
        status_code=403,
        delay_ms=40,
        recover_status=200,
        idempotency_header="Idempotency-Key",
        tags=["github", "devops", "rate-limit"],
    ),
]


def get_all_presets() -> List[dict[str, Any]]:
    """Return all preset definitions as serialized dictionaries."""
    return [p.to_dict() for p in STUDIO_PRESETS]


def get_preset_by_id(preset_id: str) -> Optional[ChaosStudioPreset]:
    """Retrieve a specific preset by its identifier."""
    for p in STUDIO_PRESETS:
        if p.id == preset_id:
            return p
    return None
