"""
Tests for RetryLab Interactive Scenario Runner & CLI Play Command.
"""

from pathlib import Path
from typer.testing import CliRunner

from retrylab.cli.main import app
from retrylab.models import FaultScenario, FaultType
from retrylab.scenarios.sequential import ScenarioStep, SequentialScenario, StepKind
from retrylab.tui.runner import InteractiveScenarioRunner

runner = CliRunner()


def test_interactive_runner_single_fault(tmp_path: Path):
    """Verify live scenario runner with single fault and clean recovery."""
    scenario = FaultScenario(
        name="stripe_timeout_recovery",
        target="https://api.stripe.com/v1/charges",
        fault=FaultType.TIMEOUT,
        fail_count=1,
    )

    runner_instance = InteractiveScenarioRunner(scenario=scenario)
    report = runner_instance.run(auto_delay=0.0, interactive_step=False)

    assert report.total_requests == 2
    assert report.faults_injected == 1
    assert report.recovery_successful is True
    assert report.idempotency_passed is True
    assert report.backoff_passed is True


def test_interactive_runner_sequential_steps(tmp_path: Path):
    """Verify live scenario runner with multi-step sequential outage."""
    scenario = SequentialScenario(
        name="multi_outage_simulation",
        target="https://api.openai.com/v1/chat/completions",
        steps=[
            ScenarioStep(kind=StepKind.FAULT, fault_type=FaultType.RATE_LIMIT_429, repeat=1),
            ScenarioStep(kind=StepKind.FAULT, fault_type=FaultType.SERVER_ERROR_500, repeat=1),
            ScenarioStep(kind=StepKind.RECOVER, status_code=200, repeat=1),
        ],
    )

    runner_instance = InteractiveScenarioRunner(scenario=scenario)
    report = runner_instance.run(auto_delay=0.0, interactive_step=False)

    assert report.total_requests == 3
    assert report.faults_injected == 2
    assert report.recovery_successful is True


def test_cli_play_command(tmp_path: Path):
    """Verify CLI `retrylab play <scenario_yaml>` runs successfully."""
    yaml_content = """
version: 1
name: cli_playback_test
target: https://api.stripe.com/v1/charges
method: POST
fault: timeout
fail_count: 1
delay: 0.01s
"""
    yaml_file = tmp_path / "playback.yaml"
    yaml_file.write_text(yaml_content.strip(), encoding="utf-8")

    result = runner.invoke(app, ["play", str(yaml_file), "--delay", "0.0"])
    assert result.exit_code == 0
    assert "LIVE CHAOS SCENARIO PLAYBACK" in result.stdout
    assert "cli_playback_test" in result.stdout
    assert "Resilience Outcome" in result.stdout
    assert "PASSED" in result.stdout


def test_cli_play_missing_file():
    """Verify CLI `retrylab play` fails cleanly with non-existent file."""
    result = runner.invoke(app, ["play", "missing_scenario_file.yaml"])
    assert result.exit_code == 1
    assert "Could not load scenario" in result.stdout
