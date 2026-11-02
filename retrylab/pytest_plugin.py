"""
RetryLab Pytest Plugin.
Registers custom fixtures and markers for zero-boilerplate testing.
"""

from typing import Any, Callable, Generator
import pytest
import httpx
import requests

from retrylab.adapters.requests_adapter import RetryLabAdapter
from retrylab.context import simulate_fault
from retrylab.idempotency import IdempotencyAuditor
from retrylab.models import FaultScenario, FaultType
from retrylab.transport import RetryLabTransport


@pytest.fixture
def retrylab_auditor() -> IdempotencyAuditor:
    """Provides an IdempotencyAuditor instance."""
    return IdempotencyAuditor(idempotency_header="Idempotency-Key")


@pytest.fixture
def make_fault_client() -> Callable[..., httpx.Client]:
    """Factory fixture returning an httpx.Client bound to a FaultScenario."""
    def _factory(scenario: FaultScenario) -> httpx.Client:
        transport = RetryLabTransport(scenario=scenario)
        return httpx.Client(transport=transport)
    return _factory


@pytest.fixture
def make_fault_session() -> Callable[..., requests.Session]:
    """Factory fixture returning a requests.Session bound with RetryLabAdapter."""
    def _factory(scenario: FaultScenario) -> requests.Session:
        session = requests.Session()
        clean_prefix = scenario.target.rstrip("*")
        session.mount(clean_prefix, RetryLabAdapter(scenario=scenario))
        return session
    return _factory


@pytest.fixture
def fault_simulation() -> Callable[..., Any]:
    """Fixture providing the simulate_fault context manager."""
    return simulate_fault
