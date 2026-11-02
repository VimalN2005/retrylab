"""
RetryLab Declarative YAML Scenario Loader.
Parses, validates, and instantiates resilience scenarios from YAML files or strings.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Union
import yaml

from retrylab.exceptions import ScenarioValidationError
from retrylab.models import FaultScenario, FaultType
from retrylab.scenarios.sequential import SequentialScenario
from retrylab.scenarios.steps import ScenarioStep, StepKind

ScenarioInstance = Union[FaultScenario, SequentialScenario]


def _parse_delay(delay_val: Any) -> float:
    """Parses delay string (e.g. '0.5s', '500ms') or numeric into seconds float."""
    if delay_val is None:
        return 0.0
    if isinstance(delay_val, (int, float)):
        return max(0.0, float(delay_val))
    if isinstance(delay_val, str):
        val = delay_val.strip().lower()
        if val.endswith("ms"):
            return max(0.0, float(val[:-2]) / 1000.0)
        if val.endswith("s"):
            return max(0.0, float(val[:-1]))
        return max(0.0, float(val))
    return 0.0


def _parse_step(raw_step: dict[str, Any]) -> ScenarioStep:
    """Normalizes and validates a single scenario step from dict."""
    kind_str = str(raw_step.get("kind", "fault")).lower()
    kind = StepKind(kind_str)

    fault_type_str = raw_step.get("type") or raw_step.get("fault_type") or "server_error_500"
    try:
        fault_type = FaultType(str(fault_type_str).lower())
    except ValueError:
        fault_type = FaultType.SERVER_ERROR_500

    delay_val = raw_step.get("delay") or raw_step.get("delay_seconds", 0.0)
    delay_seconds = _parse_delay(delay_val)

    status_code = raw_step.get("code") or raw_step.get("status_code")
    retry_after = raw_step.get("retry_after") or raw_step.get("retry_after_seconds", 2)
    body = raw_step.get("body")
    if isinstance(body, dict):
        import json
        body = json.dumps(body)

    headers = raw_step.get("headers", {})
    repeat = int(raw_step.get("repeat", 1))

    return ScenarioStep(
        kind=kind,
        fault_type=fault_type,
        status_code=int(status_code) if status_code else None,
        delay_seconds=delay_seconds,
        retry_after_seconds=int(retry_after),
        headers=headers,
        body=body,
        repeat=repeat,
    )


def load_scenario_from_yaml(source: str | Path) -> ScenarioInstance:
    """
    Loads and validates a scenario from a YAML file path or YAML content string.
    Returns either a FaultScenario or a SequentialScenario.
    """
    raw_content: str
    source_path: Path | None = None

    if isinstance(source, Path) or (isinstance(source, str) and "\n" not in source and os.path.exists(source)):
        source_path = Path(source)
        try:
            raw_content = source_path.read_text(encoding="utf-8")
        except Exception as e:
            raise ScenarioValidationError(f"Could not read YAML file '{source}': {e}") from e
    else:
        raw_content = str(source)

    try:
        parsed: dict[str, Any] = yaml.safe_load(raw_content)
    except Exception as e:
        raise ScenarioValidationError(f"Invalid YAML syntax: {e}") from e

    if not isinstance(parsed, dict):
        raise ScenarioValidationError("Scenario YAML root must be a mapping/dict.")

    name = str(parsed.get("name", "unnamed_scenario"))
    target = parsed.get("target") or (parsed.get("match", {}).get("url") if isinstance(parsed.get("match"), dict) else None)
    if not target:
        raise ScenarioValidationError("Missing required 'target' or 'match.url' in scenario YAML.")

    method = parsed.get("method") or (parsed.get("match", {}).get("method") if isinstance(parsed.get("match"), dict) else None)

    # 1. Multi-step sequential scenario
    if "steps" in parsed and isinstance(parsed["steps"], list) and len(parsed["steps"]) > 0:
        steps = [_parse_step(s) for s in parsed["steps"]]
        repeat_last = bool(parsed.get("repeat_last", True))
        return SequentialScenario(
            name=name,
            target=str(target),
            method=str(method).upper() if method else None,
            steps=steps,
            repeat_last=repeat_last,
        )

    # 2. Single-step FaultScenario
    fault_str = str(parsed.get("fault", "server_error_500")).lower()
    try:
        fault_type = FaultType(fault_str)
    except ValueError:
        raise ScenarioValidationError(f"Unknown fault type '{fault_str}'.")

    fail_count = int(parsed.get("fail_count", 1))
    delay_val = parsed.get("delay") or parsed.get("delay_seconds", 0.0)
    delay_seconds = _parse_delay(delay_val)
    status_code = parsed.get("status_code") or parsed.get("code")
    retry_after = parsed.get("retry_after") or parsed.get("retry_after_seconds", 2)
    custom_body = parsed.get("body") or parsed.get("custom_body")
    if isinstance(custom_body, dict):
        import json
        custom_body = json.dumps(custom_body)

    custom_headers = parsed.get("headers") or parsed.get("custom_headers", {})

    return FaultScenario(
        name=name,
        target=str(target),
        method=str(method).upper() if method else None,
        fault=fault_type,
        fail_count=fail_count,
        delay_seconds=delay_seconds,
        status_code=int(status_code) if status_code else None,
        retry_after_seconds=int(retry_after),
        custom_body=custom_body,
        custom_headers=custom_headers,
    )


def load_scenarios_from_dir(dir_path: str | Path) -> dict[str, ScenarioInstance]:
    """Loads all .yaml and .yml files within a directory, returning a dict of {name: Scenario}."""
    path = Path(dir_path)
    if not path.is_dir():
        raise ScenarioValidationError(f"Directory '{dir_path}' does not exist.")

    scenarios: dict[str, ScenarioInstance] = {}
    for entry in sorted(path.glob("*")):
        if entry.suffix.lower() in (".yaml", ".yml"):
            scenario = load_scenario_from_yaml(entry)
            scenarios[scenario.name] = scenario

    return scenarios
