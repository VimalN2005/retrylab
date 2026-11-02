"""
RetryLab Multi-Format Reliability Report Generator.
Generates beautiful self-contained HTML dashboards, GitHub Actions Markdown summaries, and JSON reports.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Union
from pydantic import BaseModel, Field

from retrylab.assertions.backoff import BackoffAuditor
from retrylab.idempotency import IdempotencyAuditor
from retrylab.models import FaultScenario
from retrylab.scenarios.sequential import SequentialScenario

ScenarioInstance = Union[FaultScenario, SequentialScenario]


class ReliabilityReport(BaseModel):
    """Encapsulates test outcomes, audit results, and timing metrics."""

    scenario_name: str
    target: str
    status: str = "PASS"  # PASS or FAIL
    total_requests: int = 0
    faults_injected: int = 0
    recovery_successful: bool = True
    idempotency_passed: bool = True
    idempotency_violations: list[str] = Field(default_factory=list)
    backoff_passed: bool = True
    backoff_violations: list[str] = Field(default_factory=list)
    records: list[dict[str, Any]] = Field(default_factory=list)

    def to_json(self, indent: int = 2) -> str:
        """Serializes report to formatted JSON string."""
        return json.dumps(self.model_dump(), indent=indent)

    def to_markdown(self) -> str:
        """Generates a GitHub-flavored Markdown report suitable for PR comments and CI summaries."""
        status_badge = "🟢 PASS" if self.status == "PASS" else "🔴 FAIL"
        idemp_badge = "✅ PASS" if self.idempotency_passed else "❌ FAIL"
        backoff_badge = "✅ PASS" if self.backoff_passed else "❌ FAIL"
        recov_badge = "✅ RECOVERED" if self.recovery_successful else "❌ UNRECOVERED"

        md = [
            f"# 🧪 RetryLab Reliability Report: {self.scenario_name}",
            "",
            f"**Target:** `{self.target}`  ",
            f"**Overall Status:** {status_badge}  ",
            "",
            "### 📊 Key Resilience Metrics",
            "| Metric | Result | Description |",
            "| :--- | :---: | :--- |",
            f"| **Total Outbound Requests** | `{self.total_requests}` | Total matching requests observed |",
            f"| **Faults Injected** | `{self.faults_injected}` | Simulated timeouts, 429s, or 500s |",
            f"| **Recovery Status** | {recov_badge} | Service successfully recovered |",
            f"| **Idempotency Guard** | {idemp_badge} | Zero double charges or payload mutations |",
            f"| **Backoff & Timing** | {backoff_badge} | Exponential delays respected |",
            "",
        ]

        if self.idempotency_violations:
            md.append("### ⚠️ Idempotency Violations")
            for v in self.idempotency_violations:
                md.append(f"- {v}")
            md.append("")

        if self.backoff_violations:
            md.append("### ⚠️ Backoff & Budget Violations")
            for b in self.backoff_violations:
                md.append(f"- {b}")
            md.append("")

        md.append("### 📜 Intercepted Request Log")
        md.append("| # | Method | URL | Fault Injected? |")
        md.append("| :-: | :--- | :--- | :---: |")
        for idx, r in enumerate(self.records, 1):
            injected_str = "💥 " + str(r.get("injected_fault") or "Yes") if r.get("was_fault_injected") else "✅ None"
            md.append(f"| {idx} | `{r.get('method')}` | `{r.get('url')}` | {injected_str} |")

        md.append("\n*Generated automatically by [RetryLab](https://github.com/VimalN2005/retrylab)*")
        return "\n".join(md)

    def to_html(self) -> str:
        """Generates a standalone, dark-themed self-contained HTML report."""
        status_color = "#10b981" if self.status == "PASS" else "#ef4444"
        rows = []
        for idx, r in enumerate(self.records, 1):
            injected_badge = (
                f"<span style='color:#f87171;'>💥 {r.get('injected_fault')}</span>"
                if r.get("was_fault_injected")
                else "<span style='color:#34d399;'>✅ Normal</span>"
            )
            rows.append(
                f"<tr><td>#{idx}</td><td><b>{r.get('method')}</b></td><td>{r.get('url')}</td><td>{injected_badge}</td></tr>"
            )

        table_rows = "\n".join(rows)

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>RetryLab Report - {self.scenario_name}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 2rem; }}
    .container {{ max-width: 900px; margin: 0 auto; background: #1e293b; border-radius: 12px; padding: 2rem; border: 1px solid #334155; }}
    h1 {{ margin-top: 0; display: flex; align-items: center; justify-content: space-between; font-size: 1.5rem; }}
    .badge {{ background: {status_color}; color: #fff; padding: 4px 12px; border-radius: 9999px; font-size: 0.85rem; font-weight: bold; }}
    .grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem; margin: 1.5rem 0; }}
    .card {{ background: #0f172a; padding: 1rem; border-radius: 8px; border: 1px solid #334155; text-align: center; }}
    .card .val {{ font-size: 1.5rem; font-weight: bold; color: #38bdf8; }}
    .card .lbl {{ font-size: 0.75rem; color: #94a3b8; margin-top: 4px; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 1rem; }}
    th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #334155; font-size: 0.9rem; }}
    th {{ background: #0f172a; color: #94a3b8; }}
    footer {{ text-align: center; margin-top: 2rem; font-size: 0.8rem; color: #64748b; }}
  </style>
</head>
<body>
  <div class="container">
    <h1>
      <span>🧪 RetryLab Report: {self.scenario_name}</span>
      <span class="badge">{self.status}</span>
    </h1>
    <p style="color:#94a3b8; font-size: 0.9rem;">Target: <code>{self.target}</code></p>
    
    <div class="grid">
      <div class="card"><div class="val">{self.total_requests}</div><div class="lbl">TOTAL REQUESTS</div></div>
      <div class="card"><div class="val">{self.faults_injected}</div><div class="lbl">FAULTS INJECTED</div></div>
      <div class="card"><div class="val">{'PASS' if self.idempotency_passed else 'FAIL'}</div><div class="lbl">IDEMPOTENCY</div></div>
      <div class="card"><div class="val">{'PASS' if self.backoff_passed else 'FAIL'}</div><div class="lbl">BACKOFF AUDIT</div></div>
    </div>

    <h3>Intercepted Activity Timeline</h3>
    <table>
      <thead><tr><th>#</th><th>Method</th><th>Target URL</th><th>Fault Injected</th></tr></thead>
      <tbody>{table_rows}</tbody>
    </table>
    
    <footer>Generated automatically by RetryLab Resilience Engine</footer>
  </div>
</body>
</html>"""

    def save(self, path: Path | str) -> None:
        """Saves report to a file, automatically determining format by file extension (.html, .md, .json)."""
        target_path = Path(path)
        ext = target_path.suffix.lower()
        if ext == ".html":
            content = self.to_html()
        elif ext in (".md", ".markdown"):
            content = self.to_markdown()
        else:
            content = self.to_json()

        target_path.write_text(content, encoding="utf-8")


def generate_reliability_report(
    scenario: ScenarioInstance,
    idempotency_header: str | None = "Idempotency-Key",
    backoff_auditor: BackoffAuditor | None = None,
) -> ReliabilityReport:
    """Constructs a comprehensive ReliabilityReport from an executed scenario."""
    records = [r.to_safe_dict() for r in scenario.recorded_requests]
    total_reqs = len(records)
    faults_count = sum(1 for r in records if r.get("was_fault_injected"))

    # Recovery status
    last_record_faulted = records[-1].get("was_fault_injected", False) if records else False
    recovered = total_reqs > faults_count and not last_record_faulted

    # Idempotency audit
    idemp_passed = True
    idemp_violations: list[str] = []
    if idempotency_header is not None:
        auditor = IdempotencyAuditor(idempotency_header=idempotency_header)
        violations = auditor.audit(scenario)
        if violations:
            idemp_passed = False
            idemp_violations = [v.message for v in violations]

    # Backoff audit
    backoff_passed = True
    backoff_violations: list[str] = []
    if backoff_auditor is not None:
        b_violations = backoff_auditor.audit(scenario)
        if b_violations:
            backoff_passed = False
            backoff_violations = [v.message for v in b_violations]

    overall_status = "PASS" if (recovered and idemp_passed and backoff_passed) else "FAIL"

    return ReliabilityReport(
        scenario_name=scenario.name,
        target=scenario.target,
        status=overall_status,
        total_requests=total_reqs,
        faults_injected=faults_count,
        recovery_successful=recovered,
        idempotency_passed=idemp_passed,
        idempotency_violations=idemp_violations,
        backoff_passed=backoff_passed,
        backoff_violations=backoff_violations,
        records=records,
    )
