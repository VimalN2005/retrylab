"""
RetryLab Doctor: Automated diagnostic health and environment verification engine.
Audits Python runtime, subpackage imports, PEP 561 types, assets, and polyglot toolchains.
"""

from __future__ import annotations

import importlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from rich.box import ASCII, ROUNDED
from rich.console import Console
from rich.table import Table

from retrylab import __version__


@dataclass
class DiagnosticCheck:
    category: str
    name: str
    status: str  # "PASS", "WARN", "FAIL", "INFO"
    message: str
    details: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DoctorReport:
    timestamp: float
    version: str
    passed: bool
    checks: List[DiagnosticCheck] = field(default_factory=list)
    summary: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "version": self.version,
            "passed": self.passed,
            "summary": self.summary,
            "checks": [c.to_dict() for c in self.checks],
        }


class RetryLabDoctor:
    """Runs a battery of automated diagnostic checks across environment, packages, and toolchains."""

    def __init__(self, repo_root: Optional[Path] = None):
        if repo_root is None:
            self.repo_root = Path(__file__).resolve().parent.parent
        else:
            self.repo_root = repo_root

    def diagnose_all(self) -> DoctorReport:
        checks: List[DiagnosticCheck] = []

        # 1. Python Runtime & Architecture
        checks.extend(self._check_python_runtime())

        # 2. Package & Submodule Import Integrity
        checks.extend(self._check_subpackage_imports())

        # 3. Asset & PEP 561 File Integrity
        checks.extend(self._check_file_assets())

        # 4. Polyglot Toolchains (Go, Node.js)
        checks.extend(self._check_polyglot_toolchains())

        # 5. Terminal Capabilities
        checks.extend(self._check_terminal_capabilities())

        # Calculate summary
        summary = {"PASS": 0, "WARN": 0, "FAIL": 0, "INFO": 0}
        for c in checks:
            summary[c.status] = summary.get(c.status, 0) + 1

        overall_passed = summary["FAIL"] == 0

        return DoctorReport(
            timestamp=time.time(),
            version=__version__,
            passed=overall_passed,
            checks=checks,
            summary=summary,
        )

    def _check_python_runtime(self) -> List[DiagnosticCheck]:
        results: List[DiagnosticCheck] = []
        major, minor, micro = sys.version_info[:3]
        py_ver_str = f"{major}.{minor}.{micro}"

        # Check Python >= 3.10
        if (major, minor) >= (3, 10):
            results.append(DiagnosticCheck(
                category="Runtime",
                name="Python Version",
                status="PASS",
                message=f"Python {py_ver_str} meets requirement (>=3.10)",
            ))
        else:
            results.append(DiagnosticCheck(
                category="Runtime",
                name="Python Version",
                status="FAIL",
                message=f"Python {py_ver_str} is below required 3.10+",
            ))

        # Check 64-bit architecture
        arch = platform.architecture()[0]
        results.append(DiagnosticCheck(
            category="Runtime",
            name="Architecture",
            status="PASS" if "64" in arch else "WARN",
            message=f"{platform.machine()} ({arch}) on {platform.system()}",
        ))

        return results

    def _check_subpackage_imports(self) -> List[DiagnosticCheck]:
        results: List[DiagnosticCheck] = []
        submodules = [
            ("retrylab.models", "Core scenario & fault models"),
            ("retrylab.transport", "HTTPX sync/async transport interceptor"),
            ("retrylab.adapters.requests_adapter", "Requests HTTP transport adapter"),
            ("retrylab.idempotency", "SHA-256 cryptographic idempotency auditor"),
            ("retrylab.assertions", "Exponential backoff timing verifier"),
            ("retrylab.tui", "Terminal TUI dashboard & scorecard evaluator"),
            ("retrylab.studio", "Chaos Studio web playground engine"),
            ("retrylab.webhooks", "Inbound webhook chaos & security auditor"),
            ("retrylab.streaming", "SSE & LLM streaming disruption generator"),
            ("retrylab.socket", "Low-level TCP socket fault simulator"),
            ("retrylab.grpc", "gRPC status code chaos & interceptor"),
            ("retrylab.benchmark", "Polyglot benchmark suite & latency reporter"),
            ("retrylab.soak", "High-concurrency soak & stress testing engine"),
            ("retrylab.tour", "Interactive guided resilience tour & onboarding engine"),
            ("retrylab.sidecar", "Zero-code containerized chaos sidecar proxy"),
            ("retrylab.tracing", "Distributed tracing & OpenTelemetry header auditor"),
            ("retrylab.geo", "Multi-region latency & geo-jitter chaos modeler"),
        ]

        for mod_name, desc in submodules:
            try:
                mod = importlib.import_module(mod_name)
                results.append(DiagnosticCheck(
                    category="Subpackages",
                    name=mod_name,
                    status="PASS",
                    message=f"Imported successfully ({desc})",
                ))
            except Exception as exc:
                results.append(DiagnosticCheck(
                    category="Subpackages",
                    name=mod_name,
                    status="FAIL",
                    message=f"Import failed: {exc}",
                ))

        return results

    def _check_file_assets(self) -> List[DiagnosticCheck]:
        results: List[DiagnosticCheck] = []

        # PEP 561 py.typed
        py_typed = self.repo_root / "retrylab" / "py.typed"
        if py_typed.exists():
            results.append(DiagnosticCheck(
                category="Assets",
                name="PEP 561 Type Marker",
                status="PASS",
                message="retrylab/py.typed present for IDE type inference",
            ))
        else:
            results.append(DiagnosticCheck(
                category="Assets",
                name="PEP 561 Type Marker",
                status="WARN",
                message="retrylab/py.typed missing (type inference may fail in external tools)",
            ))

        # MANIFEST.in
        manifest = self.repo_root / "MANIFEST.in"
        if manifest.exists():
            results.append(DiagnosticCheck(
                category="Assets",
                name="Source Manifest",
                status="PASS",
                message="MANIFEST.in present for source packaging",
            ))
        else:
            results.append(DiagnosticCheck(
                category="Assets",
                name="Source Manifest",
                status="WARN",
                message="MANIFEST.in missing at repository root",
            ))

        # Studio embedded HTML asset
        try:
            from retrylab.studio.assets import render_studio_html
            html = render_studio_html()
            if len(html) > 5000:
                results.append(DiagnosticCheck(
                    category="Assets",
                    name="Chaos Studio SPA",
                    status="PASS",
                    message=f"Embedded zero-dependency SPA verified ({len(html):,} bytes)",
                ))
            else:
                results.append(DiagnosticCheck(
                    category="Assets",
                    name="Chaos Studio SPA",
                    status="WARN",
                    message="Embedded SPA asset is unusually small",
                ))
        except Exception as exc:
            results.append(DiagnosticCheck(
                category="Assets",
                name="Chaos Studio SPA",
                status="FAIL",
                message=f"Failed to render studio HTML: {exc}",
            ))

        return results

    def _check_polyglot_toolchains(self) -> List[DiagnosticCheck]:
        results: List[DiagnosticCheck] = []

        # Check Go
        go_path = shutil.which("go")
        if go_path:
            try:
                proc = subprocess.run([go_path, "version"], capture_output=True, text=True, timeout=5)
                ver = proc.stdout.strip().replace("go version ", "")
                results.append(DiagnosticCheck(
                    category="Polyglot",
                    name="Go Toolchain",
                    status="PASS",
                    message=f"Detected: {ver}",
                ))
            except Exception:
                results.append(DiagnosticCheck(
                    category="Polyglot",
                    name="Go Toolchain",
                    status="INFO",
                    message="Binary found, but version check timed out",
                ))
        else:
            results.append(DiagnosticCheck(
                category="Polyglot",
                name="Go Toolchain",
                status="INFO",
                message="Go compiler not in PATH (Go SDK requires Go 1.22+ to build)",
            ))

        # Check Node.js
        node_path = shutil.which("node")
        if node_path:
            try:
                proc = subprocess.run([node_path, "--version"], capture_output=True, text=True, timeout=5)
                ver = proc.stdout.strip()
                results.append(DiagnosticCheck(
                    category="Polyglot",
                    name="Node.js Runtime",
                    status="PASS",
                    message=f"Detected: {ver}",
                ))
            except Exception:
                results.append(DiagnosticCheck(
                    category="Polyglot",
                    name="Node.js Runtime",
                    status="INFO",
                    message="Binary found, but version check timed out",
                ))
        else:
            results.append(DiagnosticCheck(
                category="Polyglot",
                name="Node.js Runtime",
                status="INFO",
                message="Node.js not in PATH (TypeScript SDK requires Node 20+)",
            ))

        return results

    def _check_terminal_capabilities(self) -> List[DiagnosticCheck]:
        results: List[DiagnosticCheck] = []
        encoding = (getattr(sys.stdout, "encoding", "") or "").lower()
        is_utf8 = "utf" in encoding

        results.append(DiagnosticCheck(
            category="Terminal",
            name="Console Encoding",
            status="PASS" if is_utf8 else "INFO",
            message=f"Stdout encoding is '{encoding or 'unknown'}' (UTF-8={'supported' if is_utf8 else 'ASCII fallback'})",
        ))

        return results


def render_doctor_table(report: DoctorReport, console: Optional[Console] = None) -> Table:
    """Render Rich diagnostic table from a DoctorReport."""
    if console is None:
        console = Console()

    encoding = (getattr(sys.stdout, "encoding", "") or "").lower()
    is_utf8 = "utf" in encoding
    current_box = ROUNDED if is_utf8 else ASCII

    table = Table(
        title=f"🩺 RetryLab Doctor Diagnostic Report (v{report.version})",
        box=current_box,
        expand=True,
        border_style="cyan",
    )
    table.add_column("Category", style="bold cyan", width=16)
    table.add_column("Check Name", style="bold white", width=26)
    table.add_column("Status", justify="center", width=10)
    table.add_column("Diagnostic Message", style="white")

    status_styles = {
        "PASS": "[bold green]PASS[/]",
        "WARN": "[bold yellow]WARN[/]",
        "FAIL": "[bold red]FAIL[/]",
        "INFO": "[dim cyan]INFO[/]",
    }

    for c in report.checks:
        styled_status = status_styles.get(c.status, c.status)
        table.add_row(
            c.category,
            c.name,
            styled_status,
            c.message,
        )

    return table
