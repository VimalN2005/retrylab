"""
Tests for SchemaDriftDetector contract drift inspection.
"""

import pytest
from retrylab import (
    DriftType,
    SchemaDriftDetector,
    SchemaDriftError,
)


def test_drift_matching_schemas():
    baseline = {
        "id": "ch_12345",
        "amount": 5000,
        "currency": "usd",
        "paid": True,
        "customer": {"email": "alex@example.com", "verified": True},
    }
    candidate = {
        "id": "ch_98765",
        "amount": 10000,
        "currency": "eur",
        "paid": False,
        "customer": {"email": "bob@example.com", "verified": False},
    }
    detector = SchemaDriftDetector()
    violations = detector.compare(baseline, candidate)
    assert len(violations) == 0
    detector.assert_no_drift(baseline, candidate)


def test_drift_missing_field():
    baseline = {"id": "evt_1", "type": "charge.succeeded", "data": {"status": "paid"}}
    candidate = {"id": "evt_1", "type": "charge.succeeded"}  # Missing 'data'!

    detector = SchemaDriftDetector()
    violations = detector.compare(baseline, candidate)

    assert len(violations) == 1
    assert violations[0].drift_type == DriftType.MISSING_FIELD
    assert violations[0].path == "data"

    with pytest.raises(SchemaDriftError, match="Missing expected field 'data'"):
        detector.assert_no_drift(baseline, candidate)


def test_drift_type_mismatch():
    baseline = {"amount": 5000, "paid": True}
    candidate = {"amount": "5000", "paid": True}  # String instead of int/float!

    detector = SchemaDriftDetector()
    violations = detector.compare(baseline, candidate)

    assert len(violations) == 1
    assert violations[0].drift_type == DriftType.TYPE_MISMATCH
    assert violations[0].path == "amount"
    assert violations[0].expected_type == "int"
    assert violations[0].actual_type == "str"


def test_drift_unexpected_null():
    baseline = {"transaction_id": "tx_abc", "status": "active"}
    candidate = {"transaction_id": "tx_abc", "status": None}  # Nullable violation!

    detector = SchemaDriftDetector()
    violations = detector.compare(baseline, candidate)

    assert len(violations) == 1
    assert violations[0].drift_type == DriftType.UNEXPECTED_NULL
    assert violations[0].path == "status"


def test_drift_nested_list_schema():
    baseline = {
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": "hello"}}
        ]
    }
    candidate = {
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": "hi"}},
            {"index": 1, "message": {"role": 123, "content": "hi"}},  # Role type mismatch!
        ]
    }

    detector = SchemaDriftDetector()
    violations = detector.compare(baseline, candidate)

    assert len(violations) == 1
    assert violations[0].drift_type == DriftType.TYPE_MISMATCH
    assert "choices[1].message.role" in violations[0].path


def test_drift_strict_mode_unexpected_field():
    baseline = {"id": 1, "name": "item"}
    candidate = {"id": 1, "name": "item", "internal_debug_flag": True}

    # Default permissive mode allows extra keys
    detector_permissive = SchemaDriftDetector(allow_extra_keys=True)
    assert len(detector_permissive.compare(baseline, candidate)) == 0

    # Strict mode catches unexpected keys
    detector_strict = SchemaDriftDetector(allow_extra_keys=False)
    violations = detector_strict.compare(baseline, candidate)
    assert len(violations) == 1
    assert violations[0].drift_type == DriftType.UNEXPECTED_NEW_FIELD
    assert violations[0].path == "internal_debug_flag"
