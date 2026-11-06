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
