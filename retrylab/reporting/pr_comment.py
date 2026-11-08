"""
RetryLab GitHub PR Comment Formatter.
Generates comprehensive Pull Request markdown reviews with embedded SVG scorecards,
service breakdowns, and actionable developer recommendations.
"""

from __future__ import annotations

from typing import Optional
from retrylab.tui.scorecard import ReliabilityScorecard, ScorecardGrade


def generate_pr_comment(
    scorecard: ReliabilityScorecard,
    svg_relative_path: Optional[str] = None,
    commit_sha: Optional[str] = None,
) -> str:
    """Generate a rich GitHub PR comment in markdown format."""
    status_icon = "🟢" if scorecard.letter_grade in (ScorecardGrade.A_PLUS, ScorecardGrade.A) else ("🟡" if scorecard.letter_grade == ScorecardGrade.B else "🔴")
    commit_str = f" for commit `{commit_sha[:7]}`" if commit_sha else ""

    lines = [
        f"## 🧪 RetryLab Resilience Audit: {status_icon} Grade **`{scorecard.letter_grade.value}`** ({scorecard.overall_score:.1f}/100){commit_str}",
        "",
    ]

    # Embedded SVG graphic if available
    if svg_relative_path:
        lines.extend([
            f"![RetryLab Reliability Scorecard]({svg_relative_path})",
            "",
        ])

    lines.extend([
        f"> **Resilience Verdict:** {scorecard.grade_description}  ",
        f"> **Audited Requests:** `{scorecard.total_requests}` | **Injected Faults:** `{scorecard.total_faults}` | **Recovery Rate:** `{scorecard.recovery_rate:.1f}%`",
        "",
        "### 🌐 Service Resilience Breakdown",
        "| Target Service | Requests | Faults | Recovered | Idempotency Guard | Backoff Compliance | Verdict |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: |",
    ])

    for ep in scorecard.endpoints:
        name = ep.service_name or ep.target
        rec_badge = "✅ PASS" if ep.recovered else "❌ FAIL"
        idemp_badge = "🔒 `PROTECTED`" if ep.idempotency_status == "PROTECTED" else f"⚠️ `{ep.idempotency_status}`"
        backoff_badge = "⏱️ `COMPLIANT`" if ep.backoff_status == "COMPLIANT" else f"⚠️ `{ep.backoff_status}`"
        verdict_badge = "🟢 PASS" if ep.verdict == "PASS" else ("🟡 WARN" if ep.verdict == "WARN" else "🔴 FAIL")

        lines.append(
            f"| `{name}` | `{ep.requests_count}` | `{ep.faults_count}` | {rec_badge} | {idemp_badge} | {backoff_badge} | {verdict_badge} |"
        )

    # Actionable Recommendations
    if scorecard.recommendations:
        lines.extend([
            "",
            "<details>",
            f"<summary>💡 <b>Actionable Engineering Recommendations ({len(scorecard.recommendations)})</b></summary>",
            "",
        ])
        for idx, rec in enumerate(scorecard.recommendations, 1):
            lines.append(f"{idx}. {rec}")
        lines.extend([
            "",
            "</details>",
        ])

    # Detailed Dimension Metrics
    lines.extend([
        "",
        "<details>",
        "<summary>📊 <b>Multi-Dimensional Resilience Metrics & Scoring</b></summary>",
        "",
        "| Resilience Dimension | Score | Weight | Status | Evaluation Details |",
        "| :--- | :---: | :---: | :---: | :--- |",
    ])
    for m in scorecard.metrics:
        lines.append(
            f"| **{m.name}** | `{m.score:.1f}%` | `{int(m.weight * 100)}%` | `{m.status}` | {m.details} |"
        )
    lines.extend([
        "",
        "</details>",
        "",
        "---",
        "*Automated third-party API chaos testing powered by [RetryLab](https://github.com/VimalN2005/retrylab)*",
    ])

    return "\n".join(lines)
