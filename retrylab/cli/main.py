"""
RetryLab CLI commands.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional
import typer

from retrylab import __version__
from retrylab.drift import SchemaDriftDetector
from retrylab.exceptions import ScenarioValidationError
from retrylab.models import FaultScenario
from retrylab.proxy import create_proxy_server
from retrylab.reporting import generate_reliability_report
from retrylab.scenarios import SequentialScenario, load_scenario_from_yaml, load_scenarios_from_dir
from retrylab.webhooks import (
    ChaosWebhookConfig,
    ChaosWebhookDispatcher,
    WebhookAuditReport,
    WebhookChaosMode,
    WebhookEmitter,
    WebhookEvent,
    WebhookReceiverAuditor,
    WebhookSignatureScheme,
)

app = typer.Typer(
    name="retrylab",
    help="RetryLab: Deterministic API Reliability & Chaos Engineering Toolkit.",
    no_args_is_help=True,
)


@app.command()
def version() -> None:
    """Display RetryLab version."""
    typer.echo(f"RetryLab v{__version__}")


@app.command()
def validate(
    path: Path = typer.Argument(..., help="Path to scenario YAML file or directory"),
) -> None:
    """Validate syntax and schema of one or more YAML scenario definitions."""
    if path.is_dir():
        try:
            scenarios = load_scenarios_from_dir(path)
            typer.echo(f"[PASS] Successfully validated {len(scenarios)} scenario(s) in '{path}':")
            for name, sc in scenarios.items():
                typer.echo(f"  - {name} (Target: {sc.target})")
        except ScenarioValidationError as err:
            typer.secho(f"[FAIL] Validation error in '{path}': {err}", fg=typer.colors.RED)
            raise typer.Exit(code=1)
    else:
        try:
            scenario = load_scenario_from_yaml(path)
            typer.secho(
                f"[PASS] Scenario '{scenario.name}' is valid! (Target: {scenario.target})",
                fg=typer.colors.GREEN,
            )
        except ScenarioValidationError as err:
            typer.secho(f"[FAIL] Scenario validation failed: {err}", fg=typer.colors.RED)
            raise typer.Exit(code=1)


@app.command()
def info(
    file_path: Path = typer.Argument(..., help="Path to a scenario YAML file"),
) -> None:
    """Display human-readable breakdown of a scenario's configuration and steps."""
    try:
        scenario = load_scenario_from_yaml(file_path)
    except ScenarioValidationError as err:
        typer.secho(f"[FAIL] Could not load scenario: {err}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    typer.secho(f"Scenario: {scenario.name}", bold=True)
    typer.echo(f"  Target: {scenario.target}")
    typer.echo(f"  Method: {scenario.method or 'ALL'}")

    if isinstance(scenario, SequentialScenario):
        typer.echo(f"  Type:   Multi-Step Sequential ({len(scenario.steps)} step(s))")
        for idx, step in enumerate(scenario.steps, 1):
            typer.echo(f"    Step #{idx}: [{step.kind.value.upper()}] fault={step.fault_type.value} repeat={step.repeat}")
    elif isinstance(scenario, FaultScenario):
        typer.echo("  Type:   Single Fault")
        typer.echo(f"  Fault:  {scenario.fault.value}")
        typer.echo(f"  Fails:  {scenario.fail_count} time(s)")
        typer.echo(f"  Delay:  {scenario.delay_seconds}s")


@app.command()
def drift(
    baseline: Path = typer.Argument(..., help="Path to baseline response JSON file"),
    candidate: Path = typer.Argument(..., help="Path to candidate response JSON file"),
    strict: bool = typer.Option(False, "--strict", help="Disallow extra unexpected fields"),
) -> None:
    """Compare two API response JSON files to detect contract schema drift."""
    try:
        base_data = json.loads(baseline.read_text(encoding="utf-8"))
    except Exception as e:
        typer.secho(f"[ERROR] Could not read baseline file: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    try:
        cand_data = json.loads(candidate.read_text(encoding="utf-8"))
    except Exception as e:
        typer.secho(f"[ERROR] Could not read candidate file: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    detector = SchemaDriftDetector(allow_extra_keys=not strict)
    violations = detector.compare(base_data, cand_data)

    if not violations:
        typer.secho("[PASS] No schema drift detected! Candidate matches baseline contract.", fg=typer.colors.GREEN)
    else:
        typer.secho(f"[FAIL] Detected {len(violations)} schema violation(s):", fg=typer.colors.RED)
        for v in violations:
            typer.echo(f"  - [{v.drift_type.value}] {v.message}")
        raise typer.Exit(code=1)


@app.command()
def gate(
    scenario_path: Path = typer.Argument(..., help="Path to scenario YAML file"),
    report: Optional[Path] = typer.Option(None, "--report", "-r", help="Path to save report (.md, .html, .json)"),
    fail_on_error: bool = typer.Option(False, "--fail-on-error", help="Exit code 1 if audit fails"),
) -> None:
    """Execute CI reliability gate and generate Markdown/HTML summary."""
    try:
        scenario = load_scenario_from_yaml(scenario_path)
    except ScenarioValidationError as err:
        typer.secho(f"[FAIL] Could not load scenario: {err}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    # Dry-run execution through all steps to generate full audit
    import httpx
    from retrylab.transport import RetryLabTransport

    transport = RetryLabTransport(scenario=scenario)
    target_clean = scenario.target.replace("*", "test_endpoint")
    method = scenario.method or "POST"

    step_count = len(scenario.steps) if isinstance(scenario, SequentialScenario) else scenario.fail_count + 1
    with httpx.Client(transport=transport) as client:
        for _ in range(step_count):
            try:
                client.request(method, target_clean, json={"ci_test": True}, headers={"Idempotency-Key": "ci_key_1"})
            except httpx.HTTPError:
                pass

    rel_report = generate_reliability_report(scenario, idempotency_header="Idempotency-Key")

    if report is not None:
        rel_report.save(report)
        typer.secho(f"📄 Saved reliability report to '{report}'", fg=typer.colors.BLUE)

    if rel_report.status == "PASS":
        typer.secho(f"[PASS] Reliability Gate Passed: {scenario.name}", fg=typer.colors.GREEN, bold=True)
    else:
        typer.secho(f"[FAIL] Reliability Gate Failed: {scenario.name}", fg=typer.colors.RED, bold=True)
        if fail_on_error:
            raise typer.Exit(code=1)


@app.command()
def serve(
    scenario_path: Path = typer.Argument(..., help="Path to scenario YAML file"),
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host address to bind to"),
    port: int = typer.Option(8080, "--port", "-p", help="Port to listen on"),
) -> None:
    """Start local HTTP forward/mock proxy daemon for cross-language testing."""
    try:
        scenario = load_scenario_from_yaml(scenario_path)
    except ScenarioValidationError as err:
        typer.secho(f"[FAIL] Could not load scenario: {err}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    typer.secho(f"🚀 Starting RetryLab Proxy on http://{host}:{port}", fg=typer.colors.GREEN, bold=True)
    typer.echo(f"  Target:   {scenario.target}")
    typer.echo(f"  Scenario: {scenario.name}")
    typer.echo("  Health:   http://localhost:{port}/_retrylab/health")
    typer.echo("  Report:   http://localhost:{port}/_retrylab/report")
    typer.echo("\nPress Ctrl+C to terminate.")

    server = create_proxy_server(scenario, host=host, port=port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        typer.echo("\nShutting down RetryLab proxy.")
        server.shutdown()


webhook_app = typer.Typer(
    name="webhook",
    help="Webhook resilience, cryptographic signature, and chaos testing commands.",
    no_args_is_help=True,
)
app.add_typer(webhook_app, name="webhook")


@webhook_app.command(name="audit")
def webhook_audit(
    url: str = typer.Argument(..., help="Target webhook endpoint URL to audit"),
    secret: str = typer.Option(..., "--secret", "-s", help="Webhook signing secret"),
    scheme: str = typer.Option("stripe_v1", "--scheme", help="Signature scheme: stripe_v1, github_sha256, hmac_sha256"),
    check_clock_skew: bool = typer.Option(True, "--clock-skew/--no-clock-skew", help="Verify clock skew rejection"),
    format: str = typer.Option("text", "--format", "-f", help="Output format: text, json"),
) -> None:
    """Run automated resilience & security audit battery on an inbound webhook receiver."""
    try:
        sig_scheme = WebhookSignatureScheme(scheme)
    except ValueError:
        typer.secho(f"[FAIL] Invalid signature scheme '{scheme}'. Choose from: stripe_v1, github_sha256, hmac_sha256", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    typer.secho(f"🔍 Running Webhook Resilience Audit against {url} [{sig_scheme.value}]...", fg=typer.colors.CYAN)

    auditor = WebhookReceiverAuditor(
        target_url=url,
        secret=secret,
        scheme=sig_scheme,
    )

    report = auditor.run_audit(check_clock_skew=check_clock_skew)

    if format == "json":
        typer.echo(report.model_dump_json(indent=2))
    else:
        for chk in report.checks:
            badge = "[PASS]" if chk.passed else "[FAIL]"
            color = typer.colors.GREEN if chk.passed else typer.colors.RED
            typer.secho(f"{badge} {chk.check_name}: {chk.details}", fg=color)

        typer.echo("")
        if report.all_passed:
            typer.secho(f"✅ Webhook Audit Passed ({report.passed_checks}/{report.total_checks} checks passed)", fg=typer.colors.GREEN, bold=True)
        else:
            typer.secho(f"❌ Webhook Audit Failed ({report.failed_checks}/{report.total_checks} checks failed)", fg=typer.colors.RED, bold=True)

    if not report.all_passed:
        raise typer.Exit(code=1)


@webhook_app.command(name="dispatch")
def webhook_dispatch(
    url: str = typer.Argument(..., help="Target webhook endpoint URL"),
    secret: str = typer.Option(..., "--secret", "-s", help="Webhook signing secret"),
    event_type: str = typer.Option("test.event", "--event", "-e", help="Webhook event type"),
    scheme: str = typer.Option("stripe_v1", "--scheme", help="Signature scheme: stripe_v1, github_sha256, hmac_sha256"),
    chaos: str = typer.Option("none", "--chaos", "-c", help="Chaos mode: none, duplicate, invalid_signature, clock_skew"),
    duplicates: int = typer.Option(2, "--duplicates", "-d", help="Number of duplicates if chaos=duplicate"),
) -> None:
    """Dispatch a synthetic signed webhook event with optional chaos injection."""
    try:
        sig_scheme = WebhookSignatureScheme(scheme)
    except ValueError:
        typer.secho(f"[FAIL] Invalid signature scheme '{scheme}'", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    try:
        chaos_mode = WebhookChaosMode(chaos)
    except ValueError:
        typer.secho(f"[FAIL] Invalid chaos mode '{chaos}'", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    emitter = WebhookEmitter(target_url=url, secret=secret, scheme=sig_scheme)
    dispatcher = ChaosWebhookDispatcher(emitter)

    import uuid
    evt = WebhookEvent(
        event_id=f"evt_{uuid.uuid4().hex[:12]}",
        event_type=event_type,
        payload={"message": "RetryLab synthetic event", "timestamp": int(time.time())},
    )

    config = ChaosWebhookConfig(
        mode=chaos_mode,
        duplicate_count=duplicates,
    )

    typer.secho(f"⚡ Dispatching webhook event '{event_type}' to {url} (Chaos: {chaos_mode.value})...", fg=typer.colors.CYAN)
    results = dispatcher.dispatch_with_chaos(evt, config)

    for res in results:
        badge = "[PASS]" if res.success else "[WARN]"
        color = typer.colors.GREEN if res.success else typer.colors.YELLOW
        typer.secho(f"{badge} Attempt {res.attempt_index}: HTTP {res.status_code} (Event ID: {res.event_id})", fg=color)


if __name__ == "__main__":
    app()
