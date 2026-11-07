"""
RetryLab Unified Polyglot Chaos Matrix & Cross-SDK Schema Compatibility Engine.
Ensures identical failure simulation semantics across Python, Go, and TypeScript SDKs.
"""

from __future__ import annotations

import json
from typing import Any
from pydantic import BaseModel, Field


class PolyglotScenarioSchema(BaseModel):
    """
    Universal scenario specification supported identically across Python, Go, and TypeScript.
    """

    name: str
    url_pattern: str
    method: str = "ALL"
    fault: str = "http_status"  # http_status, timeout, network_error, disconnect
    fail_count: int = 1
    status_code: int = 503
    response_body: Any = Field(default_factory=lambda: {"error": "Simulated transient failure"})
    delay_ms: int = 0
    recover_status: int = 200
    recover_body: Any = Field(default_factory=lambda: {"status": "succeeded", "service": "retrylab"})


class PolyglotChaosMatrix:
    """
    Validates cross-SDK compatibility and exports native code snippets for Go and TypeScript.
    """

    SUPPORTED_FAULTS = {"http_status", "timeout", "network_error", "disconnect"}
    SUPPORTED_METHODS = {"ALL", "GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"}

    @classmethod
    def verify_compatibility(cls, scenario: PolyglotScenarioSchema) -> tuple[bool, list[str]]:
        """
        Verifies that a scenario's parameters are fully supported across all 3 SDKs.
        """
        violations: list[str] = []

        if scenario.fault not in cls.SUPPORTED_FAULTS:
            violations.append(
                f"Fault '{scenario.fault}' not in polyglot supported set: {cls.SUPPORTED_FAULTS}"
            )

        if scenario.method.upper() not in cls.SUPPORTED_METHODS:
            violations.append(
                f"Method '{scenario.method}' not in polyglot supported set: {cls.SUPPORTED_METHODS}"
            )

        if scenario.fail_count < 1:
            violations.append("fail_count must be at least 1")

        if scenario.delay_ms < 0:
            violations.append("delay_ms cannot be negative")

        return (len(violations) == 0, violations)

    @classmethod
    def to_python_snippet(cls, scenario: PolyglotScenarioSchema) -> str:
        """Exports the scenario as an idiomatic Python RetryLab FaultScenario."""
        fault_name = "SERVER_ERROR_503"
        if scenario.fault == "timeout":
            fault_name = "TIMEOUT"
        elif scenario.fault in ("disconnect", "network_error"):
            fault_name = "CONNECTION_RESET"
        elif scenario.fault == "http_status":
            if scenario.status_code == 429:
                fault_name = "RATE_LIMIT_429"
            elif scenario.status_code == 500:
                fault_name = "SERVER_ERROR_500"
            else:
                fault_name = "SERVER_ERROR_503"

        delay_sec = round(scenario.delay_ms / 1000.0, 3)
        method_arg = f'\n    method="{scenario.method}",' if scenario.method != "ALL" else ""

        return (
            f"from retrylab import FaultScenario, FaultType, RetryLabTransport\n"
            f"import httpx\n\n"
            f"scenario = FaultScenario(\n"
            f'    name="{scenario.name}",\n'
            f'    target="{scenario.url_pattern}",{method_arg}\n'
            f"    fault=FaultType.{fault_name},\n"
            f"    fail_count={scenario.fail_count},\n"
            f"    delay_seconds={delay_sec},\n"
            f")\n\n"
            f"transport = RetryLabTransport(scenario=scenario)\n"
            f"with httpx.Client(transport=transport) as client:\n"
            f'    # RetryLab intercepts and simulates the {scenario.fail_count} injected fault(s)\n'
            f'    response = client.request("{scenario.method if scenario.method != "ALL" else "GET"}", "{scenario.url_pattern.replace("*", "test")}")\n'
        )

    @classmethod
    def to_yaml_snippet(cls, scenario: PolyglotScenarioSchema) -> str:
        """Exports the scenario as a standard RetryLab YAML definition."""
        lines = [
            "version: 1",
            f"name: {scenario.name}",
            f'target: "{scenario.url_pattern}"',
        ]
        if scenario.method != "ALL":
            lines.append(f"method: {scenario.method}")
        lines.append(f"fault: {scenario.fault}")
        lines.append(f"fail_count: {scenario.fail_count}")
        if scenario.delay_ms > 0:
            lines.append(f"delay: {scenario.delay_ms / 1000.0:.2f}s")
        if scenario.status_code != 503 and scenario.fault == "http_status":
            lines.append(f"status_code: {scenario.status_code}")
        return "\n".join(lines) + "\n"

    @classmethod
    def to_go_snippet(cls, scenario: PolyglotScenarioSchema) -> str:
        """Exports the scenario as an idiomatic Go struct instantiation."""
        fault_map = {
            "http_status": "retrylab.FaultHTTPStatus",
            "timeout": "retrylab.FaultTimeout",
            "network_error": "retrylab.FaultDisconnect",
            "disconnect": "retrylab.FaultDisconnect",
        }
        go_fault = fault_map.get(scenario.fault, "retrylab.FaultHTTPStatus")
        method = "" if scenario.method == "ALL" else scenario.method
        resp_body = json.dumps(scenario.response_body)
        recover_body = json.dumps(scenario.recover_body)

        return (
            f"retrylab.Scenario{{\n"
            f'\tName:          "{scenario.name}",\n'
            f'\tURLPattern:    "{scenario.url_pattern}",\n'
            f'\tMethod:        "{method}",\n'
            f"\tFault:         {go_fault},\n"
            f"\tFailCount:     {scenario.fail_count},\n"
            f"\tStatusCode:    {scenario.status_code},\n"
            f"\tResponseBody:  `{resp_body}`,\n"
            f"\tDelay:         {scenario.delay_ms} * time.Millisecond,\n"
            f"\tRecoverStatus: {scenario.recover_status},\n"
            f"\tRecoverBody:   `{recover_body}`,\n"
            f"}}"
        )

    @classmethod
    def to_ts_snippet(cls, scenario: PolyglotScenarioSchema) -> str:
        """Exports the scenario as an idiomatic TypeScript object definition."""
        ts_fault = "network_error" if scenario.fault == "disconnect" else scenario.fault
        method_str = f'"{scenario.method}"' if scenario.method != "ALL" else "undefined"

        return (
            f"const scenario: Scenario = {{\n"
            f'  name: "{scenario.name}",\n'
            f'  urlPattern: "{scenario.url_pattern}",\n'
            f"  method: {method_str},\n"
            f'  fault: "{ts_fault}",\n'
            f"  failCount: {scenario.fail_count},\n"
            f"  statusCode: {scenario.status_code},\n"
            f"  responseBody: {json.dumps(scenario.response_body, indent=2)},\n"
            f"  delayMs: {scenario.delay_ms},\n"
            f"  recoverStatus: {scenario.recover_status},\n"
            f"  recoverBody: {json.dumps(scenario.recover_body, indent=2)},\n"
            f"}};"
        )
