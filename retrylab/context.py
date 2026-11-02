"""
RetryLab Context Manager & Dynamic Patching Engine.
Allows transparent failure simulation without modifying application client initialization.
"""

from __future__ import annotations

import functools
from typing import Any, Generator, Iterator, Union
from contextlib import contextmanager
import httpx
import requests

from retrylab.adapters.requests_adapter import RetryLabAdapter
from retrylab.models import FaultScenario, FaultType
from retrylab.scenarios.sequential import SequentialScenario
from retrylab.transport import RetryLabTransport

ScenarioInstance = Union[FaultScenario, SequentialScenario]


@contextmanager
def simulate_fault(
    target: str | ScenarioInstance,
    fault: FaultType | str = FaultType.TIMEOUT,
    fail_count: int = 1,
    delay: float = 0.0,
    retry_after: int = 2,
    status_code: int | None = None,
    body: str | None = None,
    headers: dict[str, str] | None = None,
    patch_httpx: bool = True,
    patch_requests: bool = True,
) -> Iterator[ScenarioInstance]:
    """
    Context manager that temporarily patches HTTPX and Requests client constructors
    so that matching outbound calls are intercepted by RetryLab.

    Example:
        with simulate_fault("https://api.openai.com/*", fault="rate_limit_429") as scenario:
            resp = httpx.post("https://api.openai.com/v1/chat/completions", json={...})
            assert resp.status_code == 429
            assert scenario.total_attempts == 1
    """
    if isinstance(target, (FaultScenario, SequentialScenario)):
        scenario = target
    else:
        ft = FaultType(str(fault).lower()) if isinstance(fault, str) else fault
        scenario = FaultScenario(
            target=target,
            fault=ft,
            fail_count=fail_count,
            delay_seconds=delay,
            retry_after_seconds=retry_after,
            status_code=status_code,
            custom_body=body,
            custom_headers=headers or {},
        )

    # Save original initializers
    orig_httpx_client_init = httpx.Client.__init__
    orig_requests_session_init = requests.Session.__init__

    try:
        if patch_httpx:
            @functools.wraps(orig_httpx_client_init)
            def patched_httpx_init(self: httpx.Client, *args: Any, **kwargs: Any) -> None:
                # If transport not explicitly passed, attach RetryLabTransport
                passed_transport = kwargs.get("transport")
                kwargs["transport"] = RetryLabTransport(
                    scenario=scenario,
                    passthrough_transport=passed_transport,
                )
                orig_httpx_client_init(self, *args, **kwargs)

            httpx.Client.__init__ = patched_httpx_init  # type: ignore[assignment]

        if patch_requests:
            @functools.wraps(orig_requests_session_init)
            def patched_requests_init(self: requests.Session, *args: Any, **kwargs: Any) -> None:
                orig_requests_session_init(self, *args, **kwargs)
                clean_target = scenario.target.rstrip("*")
                self.mount(clean_target, RetryLabAdapter(scenario=scenario))

            requests.Session.__init__ = patched_requests_init  # type: ignore[assignment]

        yield scenario

    finally:
        if patch_httpx:
            httpx.Client.__init__ = orig_httpx_client_init  # type: ignore[assignment]
        if patch_requests:
            requests.Session.__init__ = orig_requests_session_init  # type: ignore[assignment]
