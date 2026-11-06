"""
Tests for RetryLab Terminal UI (TUI), Scorecard Engine, and Dashboard CLI commands.
"""

import json
from pathlib import Path
from typer.testing import CliRunner

from retrylab.cli.main import app
from retrylab.reporting import ReliabilityReport
from retrylab.tui import (
    EndpointResilienceEntry,
    MetricScore,
    ReliabilityScorecard,
    ScorecardEvaluator,
    ScorecardGrade,
    display_dashboard,
    render_dashboard_layout,
)
from retrylab.tui.dashboard import (
    create_endpoints_table,
    create_header_panel,
    create_metrics_table,
    create_recommendations_panel,
)

runner = CliRunner()


def test_scorecard_grade_thresholds():
    """Verify conversion of percentage scores to letter grades."""
    g_plus, _ = ScorecardEvaluator.calculate_grade(97.5)
    assert g_plus == ScorecardGrade.A_PLUS

    g_a, _ = ScorecardEvaluator.calculate_grade(88.0)
    assert g_a == ScorecardGrade.A

    g_b, _ = ScorecardEvaluator.calculate_grade(75.0)
    assert g_b == ScorecardGrade.B

    g_c, _ = ScorecardEvaluator.calculate_grade(55.0)
    assert g_c == ScorecardGrade.C

    g_f, _ = ScorecardEvaluator.calculate_grade(40.0)
    assert g_f == ScorecardGrade.F


def test_evaluate_reports_clean_pass():
    """Verify evaluation of successful resilience reports."""
    rep1 = ReliabilityReport(
        scenario_name="stripe_checkout_test",
        target="https://api.stripe.com/v1/charges",
        status="PASS",
        total_requests=2,
        faults_injected=1,
        recovery_successful=True,
        idempotency_passed=True,
        backoff_passed=True,
    )
    rep2 = ReliabilityReport(
        scenario_name="openai_completion_test",
        target="https://api.openai.com/v1/chat/completions",
        status="PASS",
        total_requests=3,
        faults_injected=2,
        recovery_successful=True,
        idempotency_passed=True,
        backoff_passed=True,
    )

    scorecard = ScorecardEvaluator.evaluate_reports([rep1, rep2])
    assert scorecard.overall_score == 100.0
    assert scorecard.letter_grade == ScorecardGrade.A_PLUS
    assert scorecard.recovery_rate == 100.0
    assert scorecard.total_requests == 5
    assert scorecard.total_faults == 3
    assert len(scorecard.endpoints) == 2
    assert scorecard.endpoints[0].service_name == "Stripe Payments"
    assert scorecard.endpoints[1].service_name == "OpenAI LLM API"


def test_evaluate_reports_with_failures():
    """Verify evaluation of reports with failure modes and recommendations."""
    failed_rep = ReliabilityReport(
        scenario_name="unhandled_flake_test",
        target="https://api.thirdparty.com/v1/data",
        status="FAIL",
        total_requests=4,
        faults_injected=3,
        recovery_successful=False,
        idempotency_passed=False,
        idempotency_violations=["Payload was mutated between attempt 1 and 2"],
        backoff_passed=False,
        backoff_violations=["Backoff delay was zero"],
    )

    scorecard = ScorecardEvaluator.evaluate_reports([failed_rep])
    assert scorecard.overall_score < 70.0
    assert scorecard.recovery_rate == 0.0
    assert len(scorecard.recommendations) >= 3
    assert any("exponential backoff" in r.lower() for r in scorecard.recommendations)
    assert any("immutable" in r.lower() or "idempotency-key" in r.lower() for r in scorecard.recommendations)


def test_empty_and_demo_scorecards():
    """Verify empty and demonstration scorecards and exports."""
    empty = ScorecardEvaluator.generate_empty_scorecard()
    assert empty.total_requests == 0

    demo = ScorecardEvaluator.generate_demo_scorecard()
    assert demo.total_requests == 9
    assert demo.letter_grade == ScorecardGrade.A_PLUS
    assert len(demo.endpoints) == 3

    # Serialization tests
    d = demo.to_dict()
    assert isinstance(d, dict)
    assert d["overall_score"] == 96.4

    json_str = demo.to_json()
    parsed = json.loads(json_str)
    assert parsed["letter_grade"] == "A+"

    md_str = demo.to_markdown()
    assert "# RetryLab API Reliability Scorecard" in md_str
    assert "Stripe Payments" in md_str


def test_dashboard_render_components():
    """Verify Rich layout and components render without exceptions."""
    scorecard = ScorecardEvaluator.generate_demo_scorecard()

    header = create_header_panel(scorecard)
    assert header is not None

    metrics_tbl = create_metrics_table(scorecard)
    assert metrics_tbl is not None

    endpoints_tbl = create_endpoints_table(scorecard)
    assert endpoints_tbl is not None

    recs_panel = create_recommendations_panel(scorecard)
    assert recs_panel is not None

    layout = render_dashboard_layout(scorecard)
    assert layout is not None

    # Test direct print
    display_dashboard(scorecard)


def test_cli_dashboard_demo():
    """Verify `retrylab dashboard --demo` executes successfully."""
    result = runner.invoke(app, ["dashboard", "--demo"])
    assert result.exit_code == 0
    assert "RETRYLAB" in result.stdout
    assert "GRADE" in result.stdout


def test_cli_scorecard_json():
    """Verify `retrylab scorecard --demo --format json` outputs valid JSON."""
    result = runner.invoke(app, ["scorecard", "--demo", "--format", "json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert "overall_score" in data
    assert data["letter_grade"] == "A+"


def test_cli_scorecard_markdown():
    """Verify `retrylab scorecard --demo --format markdown` outputs valid Markdown."""
    result = runner.invoke(app, ["scorecard", "--demo", "--format", "markdown"])
    assert result.exit_code == 0
    assert "RetryLab API Reliability Scorecard" in result.stdout


def test_cli_scorecard_fail_threshold():
    """Verify `retrylab scorecard --fail-under` exits with code 1 when score is below threshold."""
    result = runner.invoke(app, ["scorecard", "--demo", "--fail-under", "99.9"])
    assert result.exit_code == 1
    assert "Scorecard failed threshold" in result.stdout
