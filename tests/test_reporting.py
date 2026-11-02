"""
Tests for ReliabilityReport generation, Markdown, HTML, and file persistence.
"""

import json
from pathlib import Path
import httpx
import pytest

from retrylab import (
    FaultScenario,
    FaultType,
    ReliabilityReport,
    RetryLabTransport,
    generate_reliability_report,
)


def test_generate_report_successful_recovery():
    scenario = FaultScenario(
        name="test_checkout",
        target="https://api.stripe.com/v1/charges",
        fault=FaultType.TIMEOUT,
        fail_count=1,
    )
    transport = RetryLabTransport(scenario=scenario)

    with httpx.Client(transport=transport) as client:
        try:
            client.post(
                "https://api.stripe.com/v1/charges",
                json={"amount": 2000},
                headers={"Idempotency-Key": "order_tx_001"},
            )
        except httpx.ReadTimeout:
            pass

        # Retry recovers
        client.post(
            "https://api.stripe.com/v1/charges",
            json={"amount": 2000},
            headers={"Idempotency-Key": "order_tx_001"},
        )

    report = generate_reliability_report(scenario, idempotency_header="Idempotency-Key")

    assert report.scenario_name == "test_checkout"
    assert report.target == "https://api.stripe.com/v1/charges"
    assert report.status == "PASS"
    assert report.total_requests == 2
    assert report.faults_injected == 1
    assert report.recovery_successful is True
    assert report.idempotency_passed is True


def test_report_formats_and_saving(tmp_path: Path):
    report = ReliabilityReport(
        scenario_name="demo_report",
        target="https://api.openai.com/v1/*",
        status="PASS",
        total_requests=2,
        faults_injected=1,
        recovery_successful=True,
        idempotency_passed=True,
        records=[
            {"method": "POST", "url": "https://api.openai.com/v1/chat", "was_fault_injected": True, "injected_fault": "rate_limit_429"},
            {"method": "POST", "url": "https://api.openai.com/v1/chat", "was_fault_injected": False},
        ],
    )

    # 1. JSON
    json_str = report.to_json()
    parsed = json.loads(json_str)
    assert parsed["scenario_name"] == "demo_report"

    # 2. Markdown
    md_str = report.to_markdown()
    assert "# 🧪 RetryLab Reliability Report: demo_report" in md_str
    assert "🟢 PASS" in md_str
    assert "rate_limit_429" in md_str

    # 3. HTML
    html_str = report.to_html()
    assert "<!DOCTYPE html>" in html_str
    assert "demo_report" in html_str
    assert "#10b981" in html_str  # Green status badge

    # 4. Save to files
    json_file = tmp_path / "report.json"
    md_file = tmp_path / "report.md"
    html_file = tmp_path / "report.html"

    report.save(json_file)
    report.save(md_file)
    report.save(html_file)

    assert json_file.exists() and len(json_file.read_text(encoding="utf-8")) > 50
    assert md_file.exists() and len(md_file.read_text(encoding="utf-8")) > 50
    assert html_file.exists() and len(html_file.read_text(encoding="utf-8")) > 50
