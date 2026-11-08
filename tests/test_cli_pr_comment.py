"""
Tests for RetryLab CLI `pr-comment` Command and GitHub Actions Integration.
"""

from pathlib import Path
from typer.testing import CliRunner

from retrylab.cli.main import app

runner = CliRunner()


def test_cli_pr_comment_demo_stdout():
    """Verify `retrylab pr-comment --demo` prints markdown to stdout."""
    result = runner.invoke(app, ["pr-comment", "--demo"])
    assert result.exit_code == 0
    assert "RetryLab Resilience Audit" in result.stdout
    assert "Stripe Payments" in result.stdout
    assert "Resilience Gate Passed" in result.stdout


def test_cli_pr_comment_file_generation(tmp_path: Path):
    """Verify `retrylab pr-comment` exports SVG scorecard and Markdown comment files."""
    svg_file = tmp_path / "scorecard.svg"
    md_file = tmp_path / "pr_comment.md"

    result = runner.invoke(
        app,
        [
            "pr-comment",
            "--demo",
            "--svg-out",
            str(svg_file),
            "--comment-out",
            str(md_file),
            "--commit-sha",
            "9876543210abcdef",
        ],
    )
    assert result.exit_code == 0
    assert svg_file.exists()
    assert md_file.exists()

    svg_text = svg_file.read_text(encoding="utf-8")
    assert "<svg" in svg_text
    assert "</svg>" in svg_text
    assert "RETRYLAB RELIABILITY SCORECARD" in svg_text

    md_text = md_file.read_text(encoding="utf-8")
    assert "## 🧪 RetryLab Resilience Audit" in md_text
    assert "for commit `9876543`" in md_text
    assert str(svg_file) in md_text


def test_cli_pr_comment_fail_under_threshold():
    """Verify `retrylab pr-comment` exits with code 1 when score is below threshold."""
    result = runner.invoke(app, ["pr-comment", "--demo", "--fail-under", "99.9"])
    assert result.exit_code == 1
    assert "Scorecard failed threshold" in result.stdout


def test_cli_pr_comment_with_scenario_yaml(tmp_path: Path):
    """Verify `retrylab pr-comment` audits user scenario YAML."""
    yaml_content = """
version: 1
name: pr_stripe_test
target: https://api.stripe.com/v1/charges
method: POST
fault: timeout
fail_count: 1
delay: 0.01s
"""
    yaml_file = tmp_path / "scenario.yaml"
    yaml_file.write_text(yaml_content.strip(), encoding="utf-8")

    result = runner.invoke(app, ["pr-comment", "--scenario", str(yaml_file)])
    assert result.exit_code == 0
    assert "pr_stripe_test" in result.stdout or "Stripe Payments" in result.stdout
    assert "Resilience Gate Passed" in result.stdout
