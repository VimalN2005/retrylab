"""
RetryLab Idempotency & Cryptographic Payload Mutation Auditor.
Prevents duplicate charges, lost transactions, and invalid idempotency reuse.
"""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field

from retrylab.exceptions import IdempotencyViolationError
from retrylab.models import FaultScenario, RecordedRequest


class IdempotencyViolationType(str, Enum):
    """Types of idempotency failures detected in retried requests."""

    MISSING_IDEMPOTENCY_KEY = "missing_idempotency_key"
    KEY_CHANGED_ON_RETRY = "key_changed_on_retry"
    PAYLOAD_MUTATED_WITH_SAME_KEY = "payload_mutated_with_same_key"


class IdempotencyViolation(BaseModel):
    """Details of a detected idempotency violation."""

    violation_type: IdempotencyViolationType
    message: str
    attempt_number: int
    details: dict[str, Any] = Field(default_factory=dict)


def compute_payload_hash(body: bytes) -> str:
    """
    Computes a canonical SHA-256 fingerprint of the request payload.
    If the body is valid JSON, it normalizes key ordering and whitespace first.
    """
    if not body:
        return hashlib.sha256(b"").hexdigest()

    try:
        parsed = json.loads(body.decode("utf-8"))
        # Canonical JSON string: sorted keys, compact separators
        canonical = json.dumps(parsed, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()
    except Exception:
        # Raw bytes hashing for non-JSON or malformed payloads
        return hashlib.sha256(body).hexdigest()


def _get_case_insensitive_header(headers: dict[str, str], target_header: str) -> str | None:
    """Finds a header value irrespective of case."""
    target_lower = target_header.lower()
    for k, v in headers.items():
        if k.lower() == target_lower:
            return v
    return None


class IdempotencyAuditor:
    """
    Audits recorded requests from a FaultScenario to ensure safe retry behavior.
    """

    def __init__(self, idempotency_header: str = "Idempotency-Key") -> None:
        self.idempotency_header = idempotency_header

    def audit(self, scenario: FaultScenario) -> list[IdempotencyViolation]:
        """
        Inspects all recorded requests for mutations and idempotency key safety.
        Returns a list of detected violations.
        """
        records: list[RecordedRequest] = scenario.recorded_requests
        if len(records) <= 1:
            return []  # No retries occurred; nothing to violate

        violations: list[IdempotencyViolation] = []
        first_record = records[0]
        first_key = _get_case_insensitive_header(first_record.headers, self.idempotency_header)
        first_payload_hash = compute_payload_hash(first_record.body)

        for attempt_idx, record in enumerate(records[1:], start=2):
            current_key = _get_case_insensitive_header(record.headers, self.idempotency_header)
            current_payload_hash = compute_payload_hash(record.body)

            # Check 1: Missing idempotency key on retry when initial request had one
            if first_key is not None and current_key is None:
                violations.append(
                    IdempotencyViolation(
                        violation_type=IdempotencyViolationType.MISSING_IDEMPOTENCY_KEY,
                        message=(
                            f"Attempt #{attempt_idx} is missing the '{self.idempotency_header}' "
                            f"header which was present in attempt #1 ({first_key})."
                        ),
                        attempt_number=attempt_idx,
                        details={"expected_key": first_key},
                    )
                )

            # Check 2: Idempotency key changed between retries (risk of duplicate charge)
            elif first_key is not None and current_key is not None and first_key != current_key:
                violations.append(
                    IdempotencyViolation(
                        violation_type=IdempotencyViolationType.KEY_CHANGED_ON_RETRY,
                        message=(
                            f"Attempt #{attempt_idx} changed '{self.idempotency_header}' from "
                            f"'{first_key}' to '{current_key}'. Retries must maintain the same token."
                        ),
                        attempt_number=attempt_idx,
                        details={"initial_key": first_key, "new_key": current_key},
                    )
                )

            # Check 3: Same key reused with mutated payload body (rejected by payment gateways)
            if (
                first_key is not None
                and current_key == first_key
                and first_payload_hash != current_payload_hash
            ):
                violations.append(
                    IdempotencyViolation(
                        violation_type=IdempotencyViolationType.PAYLOAD_MUTATED_WITH_SAME_KEY,
                        message=(
                            f"Attempt #{attempt_idx} reused key '{first_key}' but modified the "
                            f"request payload. Gateways (like Stripe) will reject this with HTTP 400."
                        ),
                        attempt_number=attempt_idx,
                        details={
                            "key": first_key,
                            "initial_hash": first_payload_hash,
                            "mutated_hash": current_payload_hash,
                        },
                    )
                )

        return violations

    def assert_idempotent(self, scenario: FaultScenario) -> None:
        """
        Raises IdempotencyViolationError if any idempotency violation was detected.
        """
        violations = self.audit(scenario)
        if violations:
            violation_summary = "\n".join(
                f"  - [{v.violation_type.value}] {v.message}" for v in violations
            )
            raise IdempotencyViolationError(
                f"Idempotency audit failed with {len(violations)} violation(s):\n{violation_summary}"
            )
