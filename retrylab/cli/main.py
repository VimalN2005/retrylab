"""
RetryLab CLI commands.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional
import typer

from retrylab import __version__
from retrylab.drift import SchemaDriftDetector
from retrylab.exceptions import ScenarioValidationError
from retrylab.models import FaultScenario
from retrylab.scenarios import SequentialScenario, load_scenario_from_yaml, load_scenarios_from_dir

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


if __name__ == "__main__":
    app()
