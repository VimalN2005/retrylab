"""
Tests for 'retrylab doctor' CLI command and RetryLabDoctor diagnostics.
"""

from __future__ import annotations

import json
from unittest.mock import patch
from typer.testing import CliRunner

from retrylab.cli.main import app
from retrylab.doctor import DiagnosticCheck, DoctorReport, RetryLabDoctor

runner = CliRunner()


def test_doctor_diagnose_all_structure():
    """Verify diagnose_all runs checks across all system categories and passes."""
    doctor = RetryLabDoctor()
    report = doctor.diagnose_all()

    assert isinstance(report, DoctorReport)
    assert report.passed is True
    assert report.version != ""
    assert report.summary.get("PASS", 0) >= 10
    assert report.summary.get("FAIL", 0) == 0

    categories = {c.category for c in report.checks}
    assert "Runtime" in categories
    assert "Subpackages" in categories
    assert "Assets" in categories
    assert "Polyglot" in categories
    assert "Terminal" in categories


def test_doctor_cli_table_output():
    """Verify 'retrylab doctor' prints Rich diagnostic table and passes."""
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "Doctor Diagnostic Report" in result.stdout
    assert "PASS" in result.stdout
    assert "All critical systems healthy!" in result.stdout


def test_doctor_cli_json_output():
    """Verify 'retrylab doctor --format json' returns valid structured JSON."""
    result = runner.invoke(app, ["doctor", "--format", "json"])
    assert result.exit_code == 0

    data = json.loads(result.stdout)
    assert data["passed"] is True
    assert "checks" in data
    assert len(data["checks"]) > 0
    assert data["summary"]["PASS"] > 0
    assert data["summary"]["FAIL"] == 0

    # Ensure check structure
    first_check = data["checks"][0]
    assert "category" in first_check
    assert "name" in first_check
    assert "status" in first_check
    assert "message" in first_check


def test_doctor_cli_failure_handling():
    """Verify 'retrylab doctor' exits with status code 1 when a critical check fails."""
    fake_report = DoctorReport(
        timestamp=123456.0,
        version="0.3.0-alpha.1",
        passed=False,
        checks=[
            DiagnosticCheck(
                category="Runtime",
                name="Python Version",
                status="FAIL",
                message="Python 3.7 is deprecated and unsupported.",
            )
        ],
        summary={"PASS": 0, "WARN": 0, "FAIL": 1, "INFO": 0},
    )

    with patch.object(RetryLabDoctor, "diagnose_all", return_value=fake_report):
        result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 1
        assert "FAIL" in result.stdout
        assert "Critical issues detected" in result.stdout


def test_doctor_cli_json_failure_handling():
    """Verify 'retrylab doctor --format json' exits with status code 1 on failure."""
    fake_report = DoctorReport(
        timestamp=123456.0,
        version="0.3.0-alpha.1",
        passed=False,
        checks=[
            DiagnosticCheck(
                category="Assets",
                name="PEP 561 Marker",
                status="FAIL",
                message="py.typed marker missing",
            )
        ],
        summary={"PASS": 0, "WARN": 0, "FAIL": 1, "INFO": 0},
    )

    with patch.object(RetryLabDoctor, "diagnose_all", return_value=fake_report):
        result = runner.invoke(app, ["doctor", "--format", "json"])
        assert result.exit_code == 1
        data = json.loads(result.stdout)
        assert data["passed"] is False
