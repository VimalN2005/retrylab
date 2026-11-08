"""
Tests for RetryLab SVG Visual Scorecard and GitHub PR Comment Generator.
"""

from retrylab.reporting.pr_comment import generate_pr_comment
from retrylab.reporting.svg import generate_scorecard_svg
from retrylab.tui.scorecard import (
    EndpointResilienceEntry,
    MetricScore,
    ReliabilityScorecard,
    ScorecardEvaluator,
    ScorecardGrade,
)


def test_generate_scorecard_svg_passing():
    """Verify SVG generation for a high-resilience passing scorecard."""
    scorecard = ScorecardEvaluator.generate_demo_scorecard()
    svg = generate_scorecard_svg(scorecard)

    assert svg.startswith("<svg")
    assert svg.endswith("</svg>")
    assert 'viewBox="0 0 740 340"' in svg
    assert "RETRYLAB RELIABILITY SCORECARD" in svg
    assert scorecard.letter_grade.value in svg
    assert f"{scorecard.overall_score:.1f}/100" in svg
    assert "Fault Recovery Rate" in svg
    assert "Idempotency Guard" in svg
    assert "Powered by RetryLab CI" in svg


def test_generate_scorecard_svg_critical_failure():
    """Verify SVG generation for an unrecovered critical failure scorecard."""
    metrics = [
        MetricScore(name="Fault Recovery Rate", score=20.0, weight=0.35, status="CRITICAL", details="1/5 recovered"),
        MetricScore(name="Idempotency Guard", score=40.0, weight=0.25, status="CRITICAL", details="Mutation detected"),
    ]
    endpoints = [
        EndpointResilienceEntry(
            target="https://api.stripe.com/v1/charges",
            service_name="Stripe Payments",
            requests_count=3,
            faults_count=2,
            recovered=False,
            idempotency_status="MUTATED",
            backoff_status="AGGRESSIVE",
            verdict="FAIL",
        )
    ]
    scorecard = ReliabilityScorecard(
        overall_score=35.0,
        letter_grade=ScorecardGrade.F,
        grade_description="Critical Resilience Failure (Double Charge Risk)",
        metrics=metrics,
        endpoints=endpoints,
        total_requests=3,
        total_faults=2,
        recovery_rate=33.3,
        recommendations=["Ensure request payload is immutable across retries."],
    )

    svg = generate_scorecard_svg(scorecard)
    assert 'fill="#ef4444"' in svg or "#ef4444" in svg
    assert "Critical Resilience Failure" in svg
    assert "F</text>" in svg


def test_generate_pr_comment_basic():
    """Verify markdown PR comment formatting and breakdown tables."""
    scorecard = ScorecardEvaluator.generate_demo_scorecard()
    comment = generate_pr_comment(scorecard)

    assert "## 🧪 RetryLab Resilience Audit:" in comment
    assert f"Grade **`{scorecard.letter_grade.value}`**" in comment
    assert "Service Resilience Breakdown" in comment
    assert "Stripe Payments" in comment
    assert "OpenAI LLM Inference" in comment
    assert "<details>" in comment
    assert "Actionable Engineering Recommendations" in comment
    assert "Automated third-party API chaos testing powered by [RetryLab]" in comment


def test_generate_pr_comment_with_svg_and_commit():
    """Verify markdown PR comment includes embedded SVG image and commit SHA."""
    scorecard = ScorecardEvaluator.generate_demo_scorecard()
    svg_path = ".github/assets/resilience_scorecard.svg"
    commit_sha = "abcdef1234567890"

    comment = generate_pr_comment(
        scorecard=scorecard,
        svg_relative_path=svg_path,
        commit_sha=commit_sha,
    )

    assert f"![RetryLab Reliability Scorecard]({svg_path})" in comment
    assert f"for commit `{commit_sha[:7]}`" in comment
