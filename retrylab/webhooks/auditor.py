"""
RetryLab Automated Webhook Receiver Security & Resilience Auditor.
Runs an automated test battery against an inbound webhook endpoint:
1. Valid signature acceptance (2xx)
2. Forged signature rejection (400/401/403)
3. Clock skew / expired timestamp rejection (400/401)
4. Idempotent duplicate event tolerance (no 500s or duplicated actions)
"""

from __future__ import annotations

import time
import uuid
from typing import Any
import httpx
from pydantic import BaseModel, Field

from retrylab.webhooks.chaos import ChaosWebhookConfig, ChaosWebhookDispatcher, WebhookChaosMode
from retrylab.webhooks.emitter import WebhookEmitter, WebhookEvent, WebhookSignatureScheme


class WebhookCheckResult(BaseModel):
    """Result of an individual webhook security or resilience check."""

    check_name: str
    description: str
    passed: bool
    status_code: int
    details: str


class WebhookAuditReport(BaseModel):
    """Consolidated audit report for an application's webhook endpoint."""

    target_url: str
    scheme: WebhookSignatureScheme
    total_checks: int
    passed_checks: int
    failed_checks: int
    all_passed: bool
    checks: list[WebhookCheckResult] = Field(default_factory=list)


class WebhookReceiverAuditor:
    """
    Automated auditor that exercises an inbound webhook receiver against standard
    security and resilience invariants.
    """

    def __init__(
        self,
        target_url: str,
        secret: str,
        scheme: WebhookSignatureScheme = WebhookSignatureScheme.STRIPE_V1,
        client: httpx.Client | None = None,
    ) -> None:
        self.target_url = target_url
        self.secret = secret
        self.scheme = scheme
        self.emitter = WebhookEmitter(
            target_url=target_url,
            secret=secret,
            scheme=scheme,
            client=client,
        )
        self.dispatcher = ChaosWebhookDispatcher(self.emitter)

    def run_audit(
        self,
        test_payload: dict[str, Any] | None = None,
        check_clock_skew: bool = True,
    ) -> WebhookAuditReport:
        """
        Executes the webhook audit suite against the configured target endpoint.
        """
        checks: list[WebhookCheckResult] = []
        payload = test_payload or {"event": "test_audit_ping", "timestamp": int(time.time())}

        # 1. Valid Signature Check
        valid_evt = WebhookEvent(
            event_id=f"evt_audit_valid_{uuid.uuid4().hex[:8]}",
            event_type="test.audit.ping",
            payload=payload,
        )
        res_valid = self.dispatcher.dispatch_with_chaos(
            valid_evt, ChaosWebhookConfig(mode=WebhookChaosMode.NONE)
        )[0]

        valid_passed = 200 <= res_valid.status_code < 300
        checks.append(
            WebhookCheckResult(
                check_name="valid_signature",
                description="Endpoint accepts authentically signed webhook payloads",
                passed=valid_passed,
                status_code=res_valid.status_code,
                details=f"Received status {res_valid.status_code} (expected 2xx). Response: {res_valid.response_body[:100]}",
            )
        )

        # 2. Tampered / Invalid Signature Check
        forged_evt = WebhookEvent(
            event_id=f"evt_audit_forged_{uuid.uuid4().hex[:8]}",
            event_type="test.audit.ping",
            payload=payload,
        )
        res_forged = self.dispatcher.dispatch_with_chaos(
            forged_evt,
            ChaosWebhookConfig(
                mode=WebhookChaosMode.INVALID_SIGNATURE,
                tamper_secret="wrong_unauthorized_key",
            ),
        )[0]

        # Receiver MUST reject forged signatures with 400, 401, or 403
        forged_passed = res_forged.status_code in {400, 401, 403}
        checks.append(
            WebhookCheckResult(
                check_name="forged_signature_rejection",
                description="Endpoint rejects payloads signed with an invalid secret",
                passed=forged_passed,
                status_code=res_forged.status_code,
                details=f"Received status {res_forged.status_code} (expected 400, 401, or 403).",
            )
        )

        # 3. Idempotent Duplicate Event Check
        dup_evt = WebhookEvent(
            event_id=f"evt_audit_dup_{uuid.uuid4().hex[:8]}",
            event_type="test.audit.ping",
            payload=payload,
        )
        res_dups = self.dispatcher.dispatch_with_chaos(
            dup_evt,
            ChaosWebhookConfig(mode=WebhookChaosMode.DUPLICATE, duplicate_count=2),
        )
        # Both transmissions should return 2xx and receiver must not fail with 500
        dup_passed = all(200 <= r.status_code < 300 for r in res_dups)
        checks.append(
            WebhookCheckResult(
                check_name="idempotent_duplicate_handling",
                description="Endpoint safely handles at-least-once duplicate transmissions",
                passed=dup_passed,
                status_code=res_dups[1].status_code,
                details=f"Attempt 1: {res_dups[0].status_code}, Attempt 2: {res_dups[1].status_code}.",
            )
        )

        # 4. Clock Skew / Expired Timestamp Check (if enabled)
        if check_clock_skew:
            skew_evt = WebhookEvent(
                event_id=f"evt_audit_skew_{uuid.uuid4().hex[:8]}",
                event_type="test.audit.ping",
                payload=payload,
            )
            res_skew = self.dispatcher.dispatch_with_chaos(
                skew_evt,
                ChaosWebhookConfig(
                    mode=WebhookChaosMode.CLOCK_SKEW,
                    clock_skew_seconds=1200,  # 20 minutes in past
                    skew_direction="past",
                ),
            )[0]
            # When enforcing timestamp tolerance (e.g. Stripe 5min limit), endpoint rejects expired signatures
            skew_passed = res_skew.status_code in {400, 401, 403}
            checks.append(
                WebhookCheckResult(
                    check_name="clock_skew_rejection",
                    description="Endpoint rejects stale webhook payloads exceeding timestamp tolerance",
                    passed=skew_passed,
                    status_code=res_skew.status_code,
                    details=f"Received status {res_skew.status_code} (expected rejection 400/401/403 for 20m stale timestamp).",
                )
            )

        passed_count = sum(1 for c in checks if c.passed)
        failed_count = len(checks) - passed_count

        return WebhookAuditReport(
            target_url=self.target_url,
            scheme=self.scheme,
            total_checks=len(checks),
            passed_checks=passed_count,
            failed_checks=failed_count,
            all_passed=(failed_count == 0),
            checks=checks,
        )
