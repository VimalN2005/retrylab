"""
Tests for IdempotencyAuditor and cryptographic payload verification.
"""

import json
import httpx
import pytest
from retrylab import (
    FaultScenario,
    FaultType,
    IdempotencyAuditor,
    IdempotencyViolationError,
    IdempotencyViolationType,
    RetryLabTransport,
)


def test_idempotency_clean_retries():
    scenario = FaultScenario(
        target="https://api.stripe.com/v1/charges",
        fault=FaultType.TIMEOUT,
        fail_count=1,
    )
    transport = RetryLabTransport(scenario=scenario)
    auditor = IdempotencyAuditor(idempotency_header="Idempotency-Key")

    with httpx.Client(transport=transport) as client:
        # First request times out
        try:
            client.post(
                "https://api.stripe.com/v1/charges",
                json={"amount": 5000, "currency": "usd"},
                headers={"Idempotency-Key": "tok_12345"},
            )
        except httpx.ReadTimeout:
            pass

        # Retry with SAME key and SAME payload
        client.post(
            "https://api.stripe.com/v1/charges",
            json={"amount": 5000, "currency": "usd"},
            headers={"Idempotency-Key": "tok_12345"},
        )

    violations = auditor.audit(scenario)
    assert len(violations) == 0
    # Should not raise
    auditor.assert_idempotent(scenario)


def test_idempotency_missing_key_on_retry():
    scenario = FaultScenario(
        target="https://api.stripe.com/v1/charges",
        fault=FaultType.TIMEOUT,
        fail_count=1,
    )
    transport = RetryLabTransport(scenario=scenario)
    auditor = IdempotencyAuditor(idempotency_header="Idempotency-Key")

    with httpx.Client(transport=transport) as client:
        try:
            client.post(
                "https://api.stripe.com/v1/charges",
                json={"amount": 5000},
                headers={"Idempotency-Key": "tok_12345"},
            )
        except httpx.ReadTimeout:
            pass

        # Bug: retry forgot to forward the Idempotency-Key header!
        client.post("https://api.stripe.com/v1/charges", json={"amount": 5000})

    violations = auditor.audit(scenario)
    assert len(violations) == 1
    assert violations[0].violation_type == IdempotencyViolationType.MISSING_IDEMPOTENCY_KEY

    with pytest.raises(IdempotencyViolationError, match="missing the 'Idempotency-Key' header"):
        auditor.assert_idempotent(scenario)


def test_idempotency_key_changed_on_retry():
    scenario = FaultScenario(
        target="https://api.stripe.com/v1/charges",
        fault=FaultType.TIMEOUT,
        fail_count=1,
    )
    transport = RetryLabTransport(scenario=scenario)
    auditor = IdempotencyAuditor()

    with httpx.Client(transport=transport) as client:
        try:
            client.post(
                "https://api.stripe.com/v1/charges",
                json={"amount": 5000},
                headers={"Idempotency-Key": "key_first"},
            )
        except httpx.ReadTimeout:
            pass

        # Bug: generated a NEW key for retry, risking double charge!
        client.post(
            "https://api.stripe.com/v1/charges",
            json={"amount": 5000},
            headers={"Idempotency-Key": "key_second"},
        )

    violations = auditor.audit(scenario)
    assert len(violations) == 1
    assert violations[0].violation_type == IdempotencyViolationType.KEY_CHANGED_ON_RETRY


def test_idempotency_payload_mutated_with_same_key():
    scenario = FaultScenario(
        target="https://api.stripe.com/v1/charges",
        fault=FaultType.TIMEOUT,
        fail_count=1,
    )
    transport = RetryLabTransport(scenario=scenario)
    auditor = IdempotencyAuditor()

    with httpx.Client(transport=transport) as client:
        try:
            client.post(
                "https://api.stripe.com/v1/charges",
                json={"amount": 5000},
                headers={"Idempotency-Key": "tok_fixed"},
            )
        except httpx.ReadTimeout:
            pass

        # Bug: modified payload body on retry with same idempotency key
        client.post(
            "https://api.stripe.com/v1/charges",
            json={"amount": 6000},  # Amount changed!
            headers={"Idempotency-Key": "tok_fixed"},
        )

    violations = auditor.audit(scenario)
    assert len(violations) == 1
    assert violations[0].violation_type == IdempotencyViolationType.PAYLOAD_MUTATED_WITH_SAME_KEY


def test_idempotency_json_key_order_normalization():
    scenario = FaultScenario(
        target="https://api.stripe.com/*",
        fault=FaultType.TIMEOUT,
        fail_count=1,
    )
    transport = RetryLabTransport(scenario=scenario)
    auditor = IdempotencyAuditor()

    with httpx.Client(transport=transport) as client:
        try:
            # Keys in order: a, b
            client.post(
                "https://api.stripe.com/v1/charges",
                content=json.dumps({"a": 1, "b": 2}),
                headers={"Idempotency-Key": "tok_norm", "Content-Type": "application/json"},
            )
        except httpx.ReadTimeout:
            pass

        # Retry with keys in order: b, a (semantically identical!)
        client.post(
            "https://api.stripe.com/v1/charges",
            content=json.dumps({"b": 2, "a": 1}),
            headers={"Idempotency-Key": "tok_norm", "Content-Type": "application/json"},
        )

    # Should recognize semantic equality and NOT flag as violation
    violations = auditor.audit(scenario)
    assert len(violations) == 0
