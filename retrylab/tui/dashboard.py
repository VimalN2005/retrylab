"""
RetryLab Terminal User Interface (TUI) Dashboard.
Renders beautiful interactive and snapshot terminal dashboards using Rich.
Automatically detects UTF-8 capabilities and provides rock-solid cross-platform encoding fallbacks.
"""

from __future__ import annotations

import sys
from typing import Optional
from rich import box
from rich.console import Console, Group
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from retrylab import __version__
from retrylab.tui.scorecard import ReliabilityScorecard, ScorecardGrade


def _is_utf8() -> bool:
    """Check if stdout supports full UTF-8 emojis and box drawing characters."""
    encoding = (getattr(sys.stdout, "encoding", "") or "").lower()
    return "utf" in encoding


def _glyph(utf8_symbol: str, ascii_fallback: str) -> str:
    """Return symbol based on UTF-8 terminal support."""
    return utf8_symbol if _is_utf8() else ascii_fallback


def _safe_box() -> box.Box:
    """Return rounded box on UTF-8 terminals, ascii box on legacy terminals."""
    return box.ROUNDED if _is_utf8() else box.ASCII


def _format_score_bar(score: float, width: int = 12) -> Text:
    """Render a visual bar for a 0-100 score."""
    filled = int(round((score / 100.0) * width))
    empty = width - filled
    text = Text()

    fill_char = _glyph("█", "#")
    empty_char = _glyph("░", "-")

    if score >= 90.0:
        bar_color = "bold green"
    elif score >= 75.0:
        bar_color = "bold cyan"
    elif score >= 50.0:
        bar_color = "bold yellow"
    else:
        bar_color = "bold red"

    text.append(fill_char * filled, style=bar_color)
    text.append(empty_char * empty, style="dim white")
    text.append(f" {score:.1f}%", style=bar_color)
    return text


def create_header_panel(scorecard: ReliabilityScorecard) -> Panel:
    """Create the top branding and grade summary panel."""
    grade_color = {
        ScorecardGrade.A_PLUS: "bold bright_green",
        ScorecardGrade.A: "bold green",
        ScorecardGrade.B: "bold yellow",
        ScorecardGrade.C: "bold dark_orange",
        ScorecardGrade.F: "bold red",
    }.get(scorecard.letter_grade, "bold white")

    title_icon = _glyph("🧪 ", "[*] ")
    bullet = _glyph("• ", "* ")

    title_text = Text()
    title_text.append(f"{title_icon}RETRYLAB ", style="bold cyan")
    title_text.append("API Reliability & Chaos Scorecard", style="bold white")
    title_text.append(f"  v{__version__}\n", style="dim cyan")
    title_text.append("Polyglot Chaos Verification Engine  |  Python | Go | TypeScript\n\n", style="dim white")

    grade_text = Text()
    grade_text.append("OVERALL GRADE:  ", style="bold white")
    grade_text.append(f" {scorecard.letter_grade.value} ", style=f"{grade_color} reverse")
    grade_text.append(f"  ({scorecard.overall_score:.1f}/100)  ", style="bold white")
    grade_text.append(f"--  {scorecard.grade_description}\n", style=grade_color)

    stats_text = Text()
    stats_text.append(f"{bullet}Total Calls Audited: ", style="dim white")
    stats_text.append(f"{scorecard.total_requests}  ", style="bold cyan")
    stats_text.append(f"{bullet}Injected Chaos Faults: ", style="dim white")
    stats_text.append(f"{scorecard.total_faults}  ", style="bold magenta")
    stats_text.append(f"{bullet}Fault Recovery Rate: ", style="dim white")
    stats_text.append(
        f"{scorecard.recovery_rate:.1f}%",
        style="bold green" if scorecard.recovery_rate >= 90 else "bold red",
    )

    content = Group(title_text, grade_text, stats_text)
    return Panel(
        content,
        border_style="cyan",
        box=_safe_box(),
        padding=(1, 2),
    )


def create_metrics_table(scorecard: ReliabilityScorecard) -> Table:
    """Render table of individual resilience dimensions."""
    title_icon = _glyph("📊 ", "")
    table = Table(
        title=f"{title_icon}Multi-Dimensional Resilience Metrics",
        title_style="bold cyan",
        box=_safe_box(),
        border_style="blue",
        expand=True,
    )
    table.add_column("Resilience Dimension", style="bold white", width=24, overflow="fold")
    table.add_column("Score & Visual Bar", justify="left", width=22, overflow="fold")
    table.add_column("Weight", justify="center", width=8, style="dim", overflow="fold")
    table.add_column("Status", justify="center", width=12, overflow="fold")
    table.add_column("Details", style="dim white", overflow="fold")

    status_styles = {
        "EXCELLENT": "bold green",
        "GOOD": "bold cyan",
        "WARNING": "bold yellow",
        "CRITICAL": "bold red",
    }

    for m in scorecard.metrics:
        style = status_styles.get(m.status, "white")
        table.add_row(
            m.name,
            _format_score_bar(m.score),
            f"{int(m.weight * 100)}%",
            Text(m.status, style=style),
            m.details,
        )

    return table


def create_endpoints_table(scorecard: ReliabilityScorecard) -> Table:
    """Render table of audited third-party service endpoints."""
    title_icon = _glyph("🌐 ", "")
    pass_icon = _glyph("✔ PASS", "PASS")
    fail_icon = _glyph("✖ FAIL", "FAIL")

    table = Table(
        title=f"{title_icon}Third-Party Service Resilience Audit",
        title_style="bold cyan",
        box=_safe_box(),
        border_style="blue",
        expand=True,
    )
    table.add_column("Service & Target", style="bold white")
    table.add_column("Calls / Faults", justify="center")
    table.add_column("Recovered", justify="center")
    table.add_column("Idempotency", justify="center")
    table.add_column("Backoff", justify="center")
    table.add_column("Verdict", justify="center")

    for ep in scorecard.endpoints:
        rec_text = Text(pass_icon, style="bold green") if ep.recovered else Text(fail_icon, style="bold red")

        if ep.idempotency_status == "PROTECTED":
            idemp_text = Text("PROTECTED", style="bold green")
        elif ep.idempotency_status == "MUTATED":
            idemp_text = Text("MUTATED", style="bold red")
        else:
            idemp_text = Text(ep.idempotency_status, style="bold yellow")

        if ep.backoff_status == "COMPLIANT":
            backoff_text = Text("COMPLIANT", style="bold green")
        elif ep.backoff_status == "AGGRESSIVE":
            backoff_text = Text("AGGRESSIVE", style="bold red")
        else:
            backoff_text = Text(ep.backoff_status, style="bold yellow")

        if ep.verdict == "PASS":
            verdict_text = Text(" PASS ", style="bold black on green")
        elif ep.verdict == "WARN":
            verdict_text = Text(" WARN ", style="bold black on yellow")
        else:
            verdict_text = Text(" FAIL ", style="bold white on red")

        service_info = Text()
        service_info.append(ep.service_name or "Custom Endpoint", style="bold white")
        if ep.target:
            service_info.append(f"\n{ep.target}", style="dim white")

        calls_info = Text()
        calls_info.append(f"{ep.requests_count} calls\n", style="cyan")
        calls_info.append(f"({ep.faults_count} faults)", style="magenta")

        table.add_row(
            service_info,
            calls_info,
            rec_text,
            idemp_text,
            backoff_text,
            verdict_text,
        )

    return table


def create_recommendations_panel(scorecard: ReliabilityScorecard) -> Panel:
    """Create panel containing engineering action items and recommendations."""
    title_icon = _glyph("💡 ", "* ")
    check_icon = _glyph("✔ ", "[PASS] ")

    text = Text()
    if not scorecard.recommendations:
        text.append(f"{check_icon}No critical resilience gaps detected. System meets high-availability SLA.", style="bold green")
    else:
        for idx, rec in enumerate(scorecard.recommendations, 1):
            text.append(f" {idx}. ", style="bold cyan")
            text.append(f"{rec}\n", style="white")

    return Panel(
        text,
        title=Text(f"{title_icon}Actionable Resilience Recommendations", style="bold yellow"),
        border_style="yellow",
        box=_safe_box(),
        padding=(1, 2),
    )


def render_dashboard_layout(scorecard: ReliabilityScorecard) -> Layout:
    """Render a structured Rich Layout combining all dashboard sections."""
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=8),
        Layout(name="body"),
        Layout(name="recommendations", size=max(6, len(scorecard.recommendations) + 4)),
    )

    layout["header"].update(create_header_panel(scorecard))

    layout["body"].split_column(
        Layout(create_metrics_table(scorecard), name="metrics"),
        Layout(create_endpoints_table(scorecard), name="endpoints"),
    )

    layout["recommendations"].update(create_recommendations_panel(scorecard))
    return layout


def display_dashboard(
    scorecard: ReliabilityScorecard,
    console: Optional[Console] = None,
) -> None:
    """Print the complete rendered dashboard directly to terminal console."""
    if console is None:
        console = Console()

    console.print()
    console.print(create_header_panel(scorecard))
    console.print()
    console.print(create_metrics_table(scorecard))
    console.print()
    console.print(create_endpoints_table(scorecard))
    console.print()
    console.print(create_recommendations_panel(scorecard))
    console.print()
