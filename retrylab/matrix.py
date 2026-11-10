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

    SUPPORTED_FAULTS = {
        "http_status",
        "timeout",
        "network_error",
        "disconnect",
        "dns_failure",
        "dns_timeout",
        "tls_handshake_timeout",
        "ssl_cert_verification_failed",
        "ssl_hostname_mismatch",
    }
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
        elif scenario.fault == "dns_failure":
            fault_name = "DNS_FAILURE"
        elif scenario.fault == "dns_timeout":
            fault_name = "DNS_TIMEOUT"
        elif scenario.fault == "tls_handshake_timeout":
            fault_name = "TLS_HANDSHAKE_TIMEOUT"
        elif scenario.fault == "ssl_cert_verification_failed":
            fault_name = "SSL_CERT_VERIFICATION_FAILED"
        elif scenario.fault == "ssl_hostname_mismatch":
            fault_name = "SSL_HOSTNAME_MISMATCH"
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
            "dns_failure": "retrylab.FaultDisconnect",
            "dns_timeout": "retrylab.FaultTimeout",
            "tls_handshake_timeout": "retrylab.FaultTimeout",
            "ssl_cert_verification_failed": "retrylab.FaultDisconnect",
            "ssl_hostname_mismatch": "retrylab.FaultDisconnect",
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
        ts_fault_map = {
            "disconnect": "network_error",
            "dns_failure": "dns_failure",
            "dns_timeout": "timeout",
            "tls_handshake_timeout": "timeout",
            "ssl_cert_verification_failed": "ssl_error",
            "ssl_hostname_mismatch": "ssl_error",
        }
        ts_fault = ts_fault_map.get(scenario.fault, scenario.fault)
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

    @classmethod
    def to_python_grpc_snippet(
        cls,
        method: str = "/payments.PaymentService/*",
        status: str = "UNAVAILABLE",
        fail_count: int = 1,
    ) -> str:
        """Exports an idiomatic Python gRPC client interceptor definition."""
        return (
            f"import grpc\n"
            f"from retrylab.grpc import GRPCFaultConfig, GRPCStatusCode, RetryLabUnaryClientInterceptor\n\n"
            f"config = GRPCFaultConfig(\n"
            f'    method_pattern="{method}",\n'
            f"    status_code=GRPCStatusCode.{status.upper()},\n"
            f"    fail_count={fail_count},\n"
            f")\n"
            f"interceptor = RetryLabUnaryClientInterceptor(config=config)\n"
            f'channel = grpc.intercept_channel(grpc.insecure_channel("localhost:50051"), interceptor)\n'
        )

    @classmethod
    def to_go_grpc_snippet(
        cls,
        method: str = "/payments.PaymentService/*",
        status: str = "UNAVAILABLE",
        fail_count: int = 1,
    ) -> str:
        """Exports an idiomatic Go gRPC client interceptor definition."""
        go_code_map = {
            "UNAVAILABLE": "codes.Unavailable",
            "DEADLINE_EXCEEDED": "codes.DeadlineExceeded",
            "RESOURCE_EXHAUSTED": "codes.ResourceExhausted",
            "INTERNAL": "codes.Internal",
            "UNAUTHENTICATED": "codes.Unauthenticated",
        }
        code = go_code_map.get(status.upper(), f"codes.{status.title().replace('_', '')}")

        return (
            f"import (\n"
            f'\t"google.golang.org/grpc"\n'
            f'\t"google.golang.org/grpc/codes"\n'
            f'\t"google.golang.org/grpc/status"\n'
            f")\n\n"
            f"// Attach RetryLab UnaryClientInterceptor to client connection\n"
            f"interceptor := retrylab.UnaryClientInterceptor(retrylab.GRPCFaultConfig{{\n"
            f'\tMethodPattern: "{method}",\n'
            f"\tStatusCode:    {code},\n"
            f"\tFailCount:     {fail_count},\n"
            f"}})\n"
            f'conn, err := grpc.Dial(target, grpc.WithUnaryInterceptor(interceptor), grpc.WithInsecure())\n'
        )

    @classmethod
    def to_ts_grpc_snippet(
        cls,
        method: str = "/payments.PaymentService/*",
        status: str = "UNAVAILABLE",
        fail_count: int = 1,
    ) -> str:
        """Exports an idiomatic TypeScript @grpc/grpc-js client interceptor definition."""
        return (
            f"import * as grpc from '@grpc/grpc-js';\n"
            f"import {{ createGRPCChaosInterceptor }} from '@retrylab/retrylab';\n\n"
            f"const interceptor = createGRPCChaosInterceptor({{\n"
            f'  methodPattern: "{method}",\n'
            f"  statusCode: grpc.status.{status.upper()},\n"
            f"  failCount: {fail_count},\n"
            f"}});\n\n"
            f"const client = new PaymentServiceClient('localhost:50051', grpc.credentials.createInsecure(), {{\n"
            f"  interceptors: [interceptor],\n"
            f"}});\n"
        )
