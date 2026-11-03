"""
Tests for CLI webhook commands ('retrylab webhook audit' and 'retrylab webhook dispatch').
"""

from unittest.mock import patch
import pytest
from typer.testing import CliRunner

from retrylab.cli.main import app
from retrylab.webhooks import WebhookAuditReport, WebhookCheckResult, WebhookSignatureScheme

runner = CliRunner()


def test_cli_webhook_help():
    result = runner.invoke(app, ["webhook", "--help"])
    assert result.exit_code == 0
    assert "audit" in result.stdout
    assert "dispatch" in result.stdout


def test_cli_webhook_audit_invalid_scheme():
    result = runner.invoke(app, ["webhook", "audit", "http://localhost:8000/webhook", "--secret", "sec123", "--scheme", "invalid_scheme"])
    assert result.exit_code != 0
    assert "Invalid signature scheme" in result.stdout


def test_cli_webhook_audit_mocked_success():
    fake_report = WebhookAuditReport(
        target_url="http://localhost:8000/webhook",
        scheme=WebhookSignatureScheme.STRIPE_V1,
        total_checks=3,
        passed_checks=3,
        failed_checks=0,
        all_passed=True,
        checks=[
            WebhookCheckResult(check_name="valid_sig", description="desc", passed=True, status_code=200, details="OK"),
            WebhookCheckResult(check_name="forged_sig", description="desc", passed=True, status_code=401, details="OK"),
            WebhookCheckResult(check_name="idempotent_dup", description="desc", passed=True, status_code=200, details="OK"),
        ],
    )

    with patch("retrylab.cli.main.WebhookReceiverAuditor.run_audit", return_value=fake_report):
        result = runner.invoke(app, ["webhook", "audit", "http://localhost:8000/webhook", "--secret", "sec123"])
        assert result.exit_code == 0
        assert "Webhook Audit Passed" in result.stdout
        assert "[PASS] valid_sig" in result.stdout


def test_cli_webhook_audit_json_output():
    fake_report = WebhookAuditReport(
        target_url="http://localhost:8000/webhook",
        scheme=WebhookSignatureScheme.STRIPE_V1,
        total_checks=1,
        passed_checks=1,
        failed_checks=0,
        all_passed=True,
        checks=[
            WebhookCheckResult(check_name="valid_sig", description="desc", passed=True, status_code=200, details="OK"),
        ],
    )

    with patch("retrylab.cli.main.WebhookReceiverAuditor.run_audit", return_value=fake_report):
        result = runner.invoke(app, ["webhook", "audit", "http://localhost:8000/webhook", "--secret", "sec123", "--format", "json"])
        assert result.exit_code == 0
        assert '"all_passed": true' in result.stdout
