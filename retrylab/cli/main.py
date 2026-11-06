"""
RetryLab CLI commands.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Optional
import httpx
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
    ForwardingResult,
    ForwardingRule,
    MockWebhookReceiver,
    ReceivedWebhookEvent,
    WebhookAuditReport,
    WebhookChaosMode,
    WebhookEmitter,
    WebhookEvent,
    WebhookForwarder,
    WebhookReceiverAuditor,
    WebhookReceiverFaultConfig,
    WebhookReplayEngine,
    WebhookSignatureScheme,
    create_receiver_server,
)
from retrylab.streaming import (
    ChaosStreamGenerator,
    SSEStreamParser,
    StreamingChaosConfig,
    StreamingChaosMode,
    build_anthropic_messages_stream,
    build_openai_chat_stream,
)
from retrylab.socket import (
    SocketChaosConfig,
    SocketChaosTransport,
    SocketFaultType,
)
from retrylab.tui import (
    InteractiveScenarioRunner,
    ReliabilityScorecard,
    ScorecardEvaluator,
    display_dashboard,
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


@webhook_app.command(name="listen")
def webhook_listen(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host address to bind"),
    port: int = typer.Option(8085, "--port", "-p", help="Port to listen for incoming webhooks"),
    secret: Optional[str] = typer.Option(None, "--secret", "-s", help="Webhook secret key for signature verification"),
    scheme: str = typer.Option("stripe_v1", "--scheme", help="Signature scheme: stripe_v1, github_sha256, hmac_sha256"),
    forward_to: Optional[str] = typer.Option(None, "--forward-to", "-f", help="Target URL to forward incoming webhooks to"),
    fail_first: int = typer.Option(0, "--fail-first", "-n", help="Fail the first N deliveries with HTTP status code"),
    fail_status: int = typer.Option(500, "--fail-status", help="HTTP status code to return when failing first N"),
    delay: float = typer.Option(0.0, "--delay", help="Artificial processing delay in seconds"),
) -> None:
    """Start local mock webhook receiver endpoint with signature verification & fault simulation."""
    try:
        sig_scheme = WebhookSignatureScheme(scheme)
    except ValueError:
        typer.secho(f"[FAIL] Invalid signature scheme '{scheme}'", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    forwarder: Optional[WebhookForwarder] = None
    if forward_to:
        rule = ForwardingRule(target_url=forward_to)
        forwarder = WebhookForwarder(rule=rule)

    def on_event(evt: ReceivedWebhookEvent) -> None:
        badge = "[RECV]"
        sig_info = f"Sig: {evt.signature_valid}" if evt.signature_valid is not None else "Sig: unchecked"
        fault_info = f" [Fault: {evt.injected_fault}]" if evt.injected_fault else ""
        typer.secho(
            f"{badge} {evt.event_type or 'unknown'} (ID: {evt.event_id or 'none'}) -> HTTP {evt.response_status} ({sig_info}){fault_info}",
            fg=typer.colors.CYAN if evt.response_status < 400 else typer.colors.YELLOW,
        )
        if forwarder:
            fwd_results = forwarder.forward_event(evt)
            for fwd in fwd_results:
                fwd_color = typer.colors.GREEN if fwd.success else typer.colors.RED
                typer.secho(
                    f"   └─> Forwarded to {fwd.target_url} -> HTTP {fwd.status_code} ({fwd.latency_ms}ms)",
                    fg=fwd_color,
                )

    fault_config = WebhookReceiverFaultConfig(
        fail_first_n=fail_first,
        fail_status_code=fail_status,
        delay_seconds=delay,
    )

    receiver = MockWebhookReceiver(
        secret=secret,
        scheme=sig_scheme,
        fault_config=fault_config,
        on_event_received=on_event,
    )

    typer.secho(f"🚀 Starting RetryLab Webhook Listener on http://{host}:{port}", fg=typer.colors.GREEN, bold=True)
    if secret:
        typer.echo(f"  Secret:      Configured [{sig_scheme.value}]")
    if forward_to:
        typer.echo(f"  Forward To:  {forward_to}")
    if fail_first > 0:
        typer.echo(f"  Chaos Rule:  Fail first {fail_first} delivery attempt(s) with HTTP {fail_status}")
    typer.echo(f"  Events Log:  http://localhost:{port}/_retrylab/events")
    typer.echo("\nPress Ctrl+C to terminate.")

    server = create_receiver_server(receiver, host=host, port=port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        typer.echo("\nShutting down RetryLab webhook listener.")
        server.shutdown()


@webhook_app.command(name="replay")
def webhook_replay(
    fixture_path: Path = typer.Argument(..., help="Path to recorded webhook JSON fixture file"),
    target: str = typer.Option(..., "--target", "-t", help="Target endpoint URL to replay events to"),
    interval: float = typer.Option(0.05, "--interval", "-i", help="Delay in seconds between replayed events"),
    reverse: bool = typer.Option(False, "--reverse", "-r", help="Replay in reverse order (simulate out-of-order)"),
) -> None:
    """Replay recorded webhook events against a target endpoint."""
    if not fixture_path.exists():
        typer.secho(f"[FAIL] Fixture file not found: {fixture_path}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    engine = WebhookReplayEngine()
    try:
        events = engine.load_fixture_file(fixture_path)
    except Exception as exc:
        typer.secho(f"[FAIL] Failed to load fixture: {exc}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    typer.secho(
        f"⚡ Replaying {len(events)} webhook event(s) to {target} (Reverse: {reverse})...",
        fg=typer.colors.CYAN,
        bold=True,
    )

    results = engine.replay_events(
        events=events,
        target_url=target,
        delay_between_events=interval,
        reverse_order=reverse,
    )

    for idx, res in enumerate(results, 1):
        color = typer.colors.GREEN if res.success else typer.colors.RED
        badge = "[PASS]" if res.success else "[FAIL]"
        err = f" - Error: {res.error_message}" if res.error_message else ""
        typer.secho(
            f"{badge} ({idx}/{len(results)}) Event {res.event_id or 'none'} -> HTTP {res.status_code} ({res.latency_ms}ms){err}",
            fg=color,
        )

    succeeded = sum(1 for r in results if r.success)
    failed = len(results) - succeeded
    typer.echo("")
    if failed == 0:
        typer.secho(f"✅ Replay Complete: {succeeded}/{len(results)} delivered successfully.", fg=typer.colors.GREEN, bold=True)
    else:
        typer.secho(f"❌ Replay Complete with errors: {failed}/{len(results)} failed.", fg=typer.colors.RED, bold=True)
        raise typer.Exit(code=1)


stream_app = typer.Typer(
    name="stream",
    help="Streaming response and LLM token disruption testing.",
    no_args_is_help=True,
)
app.add_typer(stream_app, name="stream")


@stream_app.command(name="simulate")
def stream_simulate(
    preset: str = typer.Option("openai", "--preset", "-p", help="AI provider preset: openai, anthropic"),
    text: str = typer.Option("The rapid brown fox leaps cleanly across the sleeping hound.", "--text", "-t", help="Simulated generated text"),
    chaos: str = typer.Option("truncate", "--chaos", "-c", help="Chaos mode: none, truncate, drop_chunks, corrupt_json, mid_stream_stall, inject_error"),
    truncate_after: int = typer.Option(4, "--truncate-after", help="Chunks emitted before premature truncation"),
    stall_seconds: float = typer.Option(0.5, "--stall-seconds", help="Stall duration in seconds"),
) -> None:
    """Simulate streaming LLM token delivery with mid-stream chaos injection."""
    try:
        chaos_mode = StreamingChaosMode(chaos)
    except ValueError:
        typer.secho(f"[FAIL] Invalid chaos mode '{chaos}'", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    typer.secho(f"🌊 Simulating {preset.upper()} Token Stream with Chaos: {chaos_mode.value.upper()}", fg=typer.colors.CYAN, bold=True)

    if preset.lower() == "anthropic":
        raw_events = build_anthropic_messages_stream(text)
    else:
        raw_events = build_openai_chat_stream(text)

    cfg = StreamingChaosConfig(
        mode=chaos_mode,
        truncate_after_chunks=truncate_after,
        stall_seconds=stall_seconds,
    )

    generator = ChaosStreamGenerator(raw_events, cfg)
    parser = SSEStreamParser()

    typer.echo("─" * 60)
    typer.secho("Client Streaming Output: ", bold=True, nl=False)

    for chunk in generator:
        events = parser.feed(chunk)
        for ev in events:
            if ev.event == "error":
                typer.secho(f"\n[STREAM ERROR EVENT] {ev.data}", fg=typer.colors.RED, bold=True)
            elif ev.data == "[DONE]":
                typer.secho("\n[STREAM COMPLETE: [DONE]]", fg=typer.colors.GREEN)
            else:
                try:
                    payload = json.loads(ev.data)
                    if "choices" in payload and payload["choices"]:
                        delta = payload["choices"][0]["delta"].get("content", "")
                        typer.secho(delta, nl=False, fg=typer.colors.YELLOW)
                    elif "delta" in payload:
                        delta = payload["delta"].get("text", "")
                        typer.secho(delta, nl=False, fg=typer.colors.YELLOW)
                except Exception:
                    typer.secho(f"\n[CORRUPTED CHUNK] {ev.data}", fg=typer.colors.RED)

    typer.echo("\n" + "─" * 60)
    if generator.fault_injected:
        typer.secho(f"💥 Fault Triggered: {generator.fault_injected}", fg=typer.colors.RED, bold=True)
    else:
        typer.secho("✅ Stream Finished with No Injected Faults", fg=typer.colors.GREEN)


socket_app = typer.Typer(
    name="socket",
    help="Low-level TCP and raw socket chaos simulation commands.",
    no_args_is_help=True,
)
app.add_typer(socket_app, name="socket")


@socket_app.command(name="simulate")
def socket_simulate(
    fault: str = typer.Option("connection_reset", "--fault", "-f", help="Fault type: connection_reset, silent_drop, slow_drip, malformed_raw, premature_close"),
    url: str = typer.Option("https://api.internal/v1/resource", "--url", "-u", help="Simulated target URL"),
    timeout: float = typer.Option(0.2, "--timeout", help="Drop timeout duration in seconds"),
    drip_rate: int = typer.Option(4, "--drip-rate", help="Bytes per chunk for slow drip"),
) -> None:
    """Simulate low-level TCP connection anomalies and test client exception handling."""
    try:
        fault_type = SocketFaultType(fault)
    except ValueError:
        typer.secho(f"[FAIL] Invalid socket fault '{fault}'. Choose from: connection_reset, silent_drop, slow_drip, malformed_raw, premature_close", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    typer.secho(f"🔌 Simulating Low-Level Socket Fault: {fault_type.value.upper()}", fg=typer.colors.CYAN, bold=True)
    typer.echo(f"  Target URL: {url}")

    cfg = SocketChaosConfig(
        fault_type=fault_type,
        drop_timeout_seconds=timeout,
        drip_bytes_per_chunk=drip_rate,
    )

    transport = SocketChaosTransport(config=cfg, default_body={"status": "ok", "message": "recovered payload"})
    client = httpx.Client(transport=transport)

    try:
        t0 = time.perf_counter()
        resp = client.get(url)
        elapsed = (time.perf_counter() - t0) * 1000.0

        if fault_type == SocketFaultType.SLOW_DRIP:
            typer.secho(f"🐢 Slow Drip Received: HTTP {resp.status_code} in {elapsed:.1f}ms (Payload: {resp.text})", fg=typer.colors.YELLOW)
        elif fault_type == SocketFaultType.MALFORMED_RAW_RESPONSE:
            typer.secho(f"⚠️ Malformed Raw Wire Bytes Received: {resp.content!r}", fg=typer.colors.YELLOW)
        else:
            typer.secho(f"✅ Response: HTTP {resp.status_code} ({elapsed:.1f}ms)", fg=typer.colors.GREEN)

    except httpx.RemoteProtocolError as exc:
        typer.secho(f"💥 Client Exception: httpx.RemoteProtocolError: {exc}", fg=typer.colors.RED, bold=True)
        typer.echo("💡 Recommendation: Catch RemoteProtocolError in client retry policy and re-attempt with backoff.")

    except httpx.ReadTimeout as exc:
        typer.secho(f"⏱️ Client Exception: httpx.ReadTimeout: {exc}", fg=typer.colors.RED, bold=True)
        typer.echo("💡 Recommendation: Configure client read timeouts (< 5s) and verify circuit breaker triggers.")

    except Exception as exc:
        typer.secho(f"💥 Caught Exception: {type(exc).__name__}: {exc}", fg=typer.colors.RED)


def _run_scenarios_and_audit(scenarios: list[Any]) -> list[ReliabilityReport]:
    from retrylab.transport import RetryLabTransport
    from retrylab.scenarios.sequential import SequentialScenario

    reports: list[ReliabilityReport] = []
    for sc in scenarios:
        transport = RetryLabTransport(scenario=sc)
        target_clean = sc.target.replace("*", "test_endpoint")
        method = sc.method or "POST"
        step_count = len(sc.steps) if isinstance(sc, SequentialScenario) else sc.fail_count + 1

        with httpx.Client(transport=transport) as client:
            for _ in range(step_count):
                try:
                    client.request(
                        method,
                        target_clean,
                        json={"audit_test": True},
                        headers={"Idempotency-Key": "scorecard_tx_1"},
                    )
                except httpx.HTTPError:
                    pass

        rep = generate_reliability_report(sc, idempotency_header="Idempotency-Key")
        reports.append(rep)
    return reports


@app.command(name="dashboard")
def dashboard_command(
    scenario: Optional[Path] = typer.Option(None, "--scenario", "-s", help="Path to scenario YAML file to audit"),
    dir: Optional[Path] = typer.Option(None, "--dir", "-d", help="Path to directory containing scenario YAML files"),
    demo: bool = typer.Option(False, "--demo", help="Display multi-service demo dashboard"),
) -> None:
    """Launch interactive Rich Terminal User Interface (TUI) Reliability Dashboard."""
    if demo or (scenario is None and dir is None):
        scorecard = ScorecardEvaluator.generate_demo_scorecard()
        display_dashboard(scorecard)
        return

    scenarios = []
    if scenario is not None:
        try:
            scenarios.append(load_scenario_from_yaml(scenario))
        except ScenarioValidationError as err:
            typer.secho(f"[FAIL] Could not load scenario '{scenario}': {err}", fg=typer.colors.RED)
            raise typer.Exit(code=1)
    elif dir is not None:
        try:
            sc_dict = load_scenarios_from_dir(dir)
            scenarios.extend(sc_dict.values())
        except ScenarioValidationError as err:
            typer.secho(f"[FAIL] Could not load scenarios from '{dir}': {err}", fg=typer.colors.RED)
            raise typer.Exit(code=1)

    reports = _run_scenarios_and_audit(scenarios)
    scorecard = ScorecardEvaluator.evaluate_reports(reports)
    display_dashboard(scorecard)


@app.command(name="scorecard")
def scorecard_command(
    scenario: Optional[Path] = typer.Option(None, "--scenario", "-s", help="Path to scenario YAML file to audit"),
    dir: Optional[Path] = typer.Option(None, "--dir", "-d", help="Path to directory containing scenario YAML files"),
    demo: bool = typer.Option(False, "--demo", help="Use multi-service demo scenario battery"),
    format: str = typer.Option("tui", "--format", "-f", help="Output format: tui, json, markdown"),
    fail_under: float = typer.Option(70.0, "--fail-under", help="Minimum required score (0-100) before exiting with code 1"),
) -> None:
    """Generate and display multi-dimensional API reliability scorecard with letter grade."""
    if demo or (scenario is None and dir is None):
        scorecard = ScorecardEvaluator.generate_demo_scorecard()
    else:
        scenarios = []
        if scenario is not None:
            try:
                scenarios.append(load_scenario_from_yaml(scenario))
            except ScenarioValidationError as err:
                typer.secho(f"[FAIL] Could not load scenario '{scenario}': {err}", fg=typer.colors.RED)
                raise typer.Exit(code=1)
        elif dir is not None:
            try:
                sc_dict = load_scenarios_from_dir(dir)
                scenarios.extend(sc_dict.values())
            except ScenarioValidationError as err:
                typer.secho(f"[FAIL] Could not load scenarios from '{dir}': {err}", fg=typer.colors.RED)
                raise typer.Exit(code=1)

        reports = _run_scenarios_and_audit(scenarios)
        scorecard = ScorecardEvaluator.evaluate_reports(reports)

    if format == "json":
        typer.echo(scorecard.to_json())
    elif format == "markdown":
        md_text = scorecard.to_markdown()
        try:
            typer.echo(md_text)
        except UnicodeEncodeError:
            safe_text = md_text.encode(sys.stdout.encoding or "ascii", errors="replace").decode(sys.stdout.encoding or "ascii")
            typer.echo(safe_text)
    else:
        display_dashboard(scorecard)

    if scorecard.overall_score < fail_under:
        typer.secho(
            f"\n[FAIL] Scorecard failed threshold: {scorecard.overall_score:.1f} < {fail_under:.1f} (Grade: {scorecard.letter_grade.value})",
            fg=typer.colors.RED,
            bold=True,
        )
        raise typer.Exit(code=1)


@app.command(name="play")
def play_command(
    scenario_path: Path = typer.Argument(..., help="Path to scenario YAML file to play"),
    step: bool = typer.Option(False, "--step", help="Wait for user input between retry attempts"),
    delay: float = typer.Option(0.05, "--delay", help="Artificial delay in seconds between attempts"),
) -> None:
    """Execute scenario with step-by-step terminal visualization and live audit."""
    try:
        scenario = load_scenario_from_yaml(scenario_path)
    except ScenarioValidationError as err:
        typer.secho(f"[FAIL] Could not load scenario '{scenario_path}': {err}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    runner = InteractiveScenarioRunner(scenario=scenario)
    report = runner.run(auto_delay=delay, interactive_step=step)

    if not report.recovery_successful or not report.idempotency_passed or not report.backoff_passed:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
