"""
RetryLab API Schema Drift & Breaking Change Detection Engine.
Detects missing fields, type mutations, and nullability violations in upstream API responses.
"""

from __future__ import annotations

import json
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field

from retrylab.exceptions import RetryLabError


class SchemaDriftError(RetryLabError):
    """Raised when an API response violates the expected contract schema."""


class DriftType(str, Enum):
    """Categories of detected schema drift."""

    MISSING_FIELD = "missing_field"
    TYPE_MISMATCH = "type_mismatch"
    UNEXPECTED_NULL = "unexpected_null"
    UNEXPECTED_NEW_FIELD = "unexpected_new_field"


class DriftViolation(BaseModel):
    """Details of an observed schema divergence."""

    drift_type: DriftType
    path: str
    expected_type: str | None = None
    actual_type: str | None = None
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class SchemaDriftDetector:
    """
    Compares candidate responses against a known baseline fixture to detect contract violations.
    """

    def __init__(
        self,
        allow_extra_keys: bool = True,
        strict_numeric_types: bool = False,
    ) -> None:
        self.allow_extra_keys = allow_extra_keys
        self.strict_numeric_types = strict_numeric_types

    def _get_type_name(self, val: Any) -> str:
        if val is None:
            return "null"
        return type(val).__name__

    def _is_compatible_type(self, expected: Any, actual: Any) -> bool:
        """Determines if actual value type matches expected type."""
        if expected is None:
            return True  # If baseline was null, any type might be valid

        if actual is None:
            return False  # Expected non-null, received null

        exp_t = type(expected)
        act_t = type(actual)

        if exp_t == act_t:
            return True

        # Numeric tolerance: int can be compatible with float if not strict
        if not self.strict_numeric_types:
            if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
                return True

        return False

    def compare(
        self,
        baseline: Any,
        candidate: Any,
        path: str = "root",
    ) -> list[DriftViolation]:
        """
        Recursively inspects candidate structure against baseline.
        Returns a list of any DriftViolation items discovered.
        """
        violations: list[DriftViolation] = []

        # Check for unexpected null
        if baseline is not None and candidate is None:
            violations.append(
                DriftViolation(
                    drift_type=DriftType.UNEXPECTED_NULL,
                    path=path,
                    expected_type=self._get_type_name(baseline),
                    actual_type="null",
                    message=f"Field '{path}' is null; expected non-null '{self._get_type_name(baseline)}'.",
                )
            )
            return violations

        # Check type compatibility
        if not self._is_compatible_type(baseline, candidate):
            violations.append(
                DriftViolation(
                    drift_type=DriftType.TYPE_MISMATCH,
                    path=path,
                    expected_type=self._get_type_name(baseline),
                    actual_type=self._get_type_name(candidate),
                    message=(
                        f"Type mismatch at '{path}': expected '{self._get_type_name(baseline)}', "
                        f"got '{self._get_type_name(candidate)}'."
                    ),
                )
            )
            return violations

        # Dict / Mapping traversal
        if isinstance(baseline, dict) and isinstance(candidate, dict):
            # Check for missing keys
            for key, exp_val in baseline.items():
                child_path = f"{path}.{key}" if path != "root" else key
                if key not in candidate:
                    violations.append(
                        DriftViolation(
                            drift_type=DriftType.MISSING_FIELD,
                            path=child_path,
                            expected_type=self._get_type_name(exp_val),
                            actual_type="missing",
                            message=f"Missing expected field '{child_path}' in response.",
                        )
                    )
                else:
                    violations.extend(self.compare(exp_val, candidate[key], child_path))

            # Check for extra keys if strict mode
            if not self.allow_extra_keys:
                for key in candidate:
                    if key not in baseline:
                        child_path = f"{path}.{key}" if path != "root" else key
                        violations.append(
                            DriftViolation(
                                drift_type=DriftType.UNEXPECTED_NEW_FIELD,
                                path=child_path,
                                actual_type=self._get_type_name(candidate[key]),
                                message=f"Unexpected new field '{child_path}' found in strict mode.",
                            )
                        )

        # List traversal
        elif isinstance(baseline, list) and isinstance(candidate, list):
            if baseline and candidate:
                # Compare elements against baseline template element
                sample_baseline = baseline[0]
                for idx, item in enumerate(candidate):
                    item_path = f"{path}[{idx}]"
                    violations.extend(self.compare(sample_baseline, item, item_path))

        return violations

    def assert_no_drift(self, baseline: Any, candidate: Any) -> None:
        """
        Raises SchemaDriftError if any breaking contract violations are detected.
        """
        violations = self.compare(baseline, candidate)
        if violations:
            summary = "\n".join(f"  - [{v.drift_type.value}] {v.message}" for v in violations)
            raise SchemaDriftError(
                f"Schema contract drift detected ({len(violations)} violation(s)):\n{summary}"
            )
