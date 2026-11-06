"""
RetryLab Interactive Scenario Runner & Live Terminal Monitor.
Provides step-through playback and live animated terminal monitoring for chaos scenarios.
"""

from __future__ import annotations

import sys
import time
from typing import Any, Optional, Union
import httpx
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from retrylab.models import FaultScenario
from retrylab.reporting.generator import ReliabilityReport, generate_reliability_report
from retrylab.scenarios.sequential import SequentialScenario
from retrylab.transport import RetryLabTransport
from retrylab.tui.dashboard import _is_utf8, _safe_box

ScenarioType = Union[FaultScenario, SequentialScenario]


class InteractiveScenarioRunner:
    """Executes a chaos scenario with step-by-step terminal visualization and live audit."""

    def __init__(
        self,
        scenario: ScenarioType,
        console: Optional[Console] = None,
        idempotency_header: str = "Idempotency-Key",
    ) -> None:
        self.scenario = scenario
        self.console = console or Console()
        self.idempotency_header = idempotency_header

    def run(
        self,
        auto_delay: float = 0.05,
        interactive_step: bool = False,
    ) -> ReliabilityReport:
        """Run scenario through simulated client requests and render live terminal progress."""
        transport = RetryLabTransport(scenario=self.scenario)
        target = self.scenario.target.replace("*", "live_resource")
        method = self.scenario.method or "POST"
        step_count = (
            len(self.scenario.steps)
            if isinstance(self.scenario, SequentialScenario)
            else self.scenario.fail_count + 1
        )

        title_icon = "🧪 " if _is_utf8() else "[*] "
        bullet = "• " if _is_utf8() else "* "

        # Header banner
        header_text = Text()
        header_text.append(f"{title_icon}LIVE CHAOS SCENARIO PLAYBACK: ", style="bold cyan")
        header_text.append(f"{self.scenario.name}\n", style="bold white")
        header_text.append(f"{bullet}Target URL: ", style="dim white")
        header_text.append(f"{self.scenario.target}  ", style="bold yellow")
        header_text.append(f"{bullet}Method: ", style="dim white")
        header_text.append(f"{method}  ", style="bold green")
        header_text.append(f"{bullet}Total Steps: ", style="dim white")
        header_text.append(f"{step_count}", style="bold magenta")

        self.console.print()
        self.console.print(
            Panel(
                header_text,
                border_style="cyan",
                box=_safe_box(),
                padding=(0, 1),
            )
        )

        dummy_payload = {"live_test": True, "action": "checkout_order", "amount": 4900}
        headers = {self.idempotency_header: f"live_idemp_{int(time.time())}"}

        with httpx.Client(transport=transport) as client:
            for step_idx in range(1, step_count + 1):
                if auto_delay > 0 and step_idx > 1:
                    time.sleep(auto_delay)

                step_card = Table(box=_safe_box(), expand=True, border_style="blue")
                step_card.add_column(f"Attempt #{step_idx} of {step_count}", style="bold white")

                t0 = time.perf_counter()
                injected_err: Optional[str] = None
                status_code: Optional[int] = None

                try:
                    resp = client.request(
                        method,
                        target,
                        json=dummy_payload,
                        headers=headers,
                        timeout=5.0,
                    )
                    status_code = resp.status_code
                except httpx.HTTPError as exc:
                    injected_err = f"{type(exc).__name__}: {exc}"

                elapsed_ms = (time.perf_counter() - t0) * 1000.0

                # Render step details
                body_text = Text()
                body_text.append(f"--> {method} {target}\n", style="bold white")
                body_text.append(f"    Idempotency: {headers[self.idempotency_header]}\n", style="dim cyan")

                if injected_err:
                    body_text.append(f"    [FAULT INJECTED] {injected_err} ({elapsed_ms:.1f}ms)\n", style="bold red")
                    body_text.append("    [CLIENT ACTION] Exception caught; initiating backoff retry...", style="yellow")
                else:
                    status_style = "bold green" if (status_code and status_code < 400) else "bold red"
                    status_label = f"HTTP {status_code}" if status_code else "UNKNOWN"
                    if status_code and status_code >= 400:
                        body_text.append(f"    [FAULT INJECTED] {status_label} ({elapsed_ms:.1f}ms)\n", style="bold red")
                        body_text.append("    [CLIENT ACTION] Non-2xx response; scheduling retry attempt...", style="yellow")
                    else:
                        body_text.append(f"    [RECOVERED] Status: {status_label} ({elapsed_ms:.1f}ms)\n", style=status_style)
                        body_text.append("    [CLIENT ACTION] Clean recovery completed successfully!", style="bold green")

                step_card.add_row(body_text)
                self.console.print(step_card)

                if interactive_step and step_idx < step_count:
                    try:
                        input("Press [Enter] to execute next attempt...")
                    except (EOFError, OSError):
                        pass

        # Generate and render summary audit report
        report = generate_reliability_report(
            scenario=self.scenario,
            idempotency_header=self.idempotency_header,
        )

        summary_box = Text()
        pass_icon = "[PASS] " if not _is_utf8() else "✔ "
        fail_icon = "[FAIL] " if not _is_utf8() else "✖ "

        if report.recovery_successful:
            summary_box.append(f"{pass_icon}SCENARIO RECOVERY: PASSED\n", style="bold green")
        else:
            summary_box.append(f"{fail_icon}SCENARIO RECOVERY: FAILED\n", style="bold red")

        if report.idempotency_passed:
            summary_box.append(f"{pass_icon}IDEMPOTENCY AUDIT: PASSED (Zero double charges)\n", style="bold green")
        else:
            summary_box.append(f"{fail_icon}IDEMPOTENCY AUDIT: FAILED (Key/Payload violation)\n", style="bold red")

        if report.backoff_passed:
            summary_box.append(f"{pass_icon}BACKOFF HYGIENE:   PASSED (Exponential backoff confirmed)", style="bold green")
        else:
            summary_box.append(f"{fail_icon}BACKOFF HYGIENE:   FAILED (Aggressive hammering detected)", style="bold red")

        self.console.print(
            Panel(
                summary_box,
                title="Resilience Outcome",
                border_style="green" if report.status == "PASS" else "red",
                box=_safe_box(),
                padding=(0, 1),
            )
        )
        self.console.print()
        return report
