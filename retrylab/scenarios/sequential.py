"""
RetryLab Multi-Step Sequential Scenario Engine.
Coordinates progressive state transitions across multiple requests.
"""

from __future__ import annotations

import fnmatch
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from retrylab.models import FaultType, RecordedRequest
from retrylab.scenarios.steps import ScenarioStep, StepKind


class SequentialScenario(BaseModel):
    """
    A stateful multi-step scenario that progresses through defined steps upon each request.
    Example sequence:
      Step 1: Timeout (repeat 1)
      Step 2: HTTP 503 (repeat 1)
      Step 3: Recover 200 OK (repeat indefinitely)
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str = "sequential_scenario"
    target: str
    method: str | None = None
    steps: list[ScenarioStep] = Field(min_length=1)
    repeat_last: bool = True

    # Internal state
    _current_step_index: int = PrivateAttr(default=0)
    _current_step_count: int = PrivateAttr(default=0)
    _attempts: int = PrivateAttr(default=0)
    _recorded_requests: list[RecordedRequest] = PrivateAttr(default_factory=list)
    _active_evaluated_step: ScenarioStep | None = PrivateAttr(default=None)

    def matches(self, url: str, method: str) -> bool:
        """Determines if the request matches target pattern and method."""
        if self.method and self.method.upper() != method.upper():
            return False

        if fnmatch.fnmatch(url, self.target):
            return True

        clean_target = self.target.rstrip("*")
        if url.startswith(clean_target):
            return True

        return False

    def get_current_step(self) -> ScenarioStep:
        """Returns the active step in the sequence."""
        if self._current_step_index < len(self.steps):
            return self.steps[self._current_step_index]
        if self.repeat_last and self.steps:
            return self.steps[-1]
        # Default fallback to 200 recover step
        return ScenarioStep(kind=StepKind.RECOVER, status_code=200)

    def _resolved_step(self) -> ScenarioStep:
        """Returns active evaluated step for the current request cycle, or current step."""
        return self._active_evaluated_step or self.get_current_step()

    def should_inject_fault(self, url: str, method: str) -> bool:
        """Returns True if the current step dictates a fault injection."""
        if not self.matches(url, method):
            return False
        # Snapshot the active step for this request cycle
        self._active_evaluated_step = self.get_current_step()
        return self._active_evaluated_step.kind == StepKind.FAULT

    def advance_step(self) -> None:
        """Advances internal state machine counter to the next step when repeat limit is reached."""
        self._current_step_count += 1
        current_step = self.get_current_step()

        if self._current_step_count >= current_step.repeat:
            if self._current_step_index < len(self.steps) - 1:
                self._current_step_index += 1
                self._current_step_count = 0

    def record_attempt(
        self,
        url: str,
        method: str,
        headers: dict[str, str],
        body: bytes,
        injected: bool,
    ) -> RecordedRequest:
        """Records the request attempt and advances the scenario sequence."""
        self._attempts += 1
        step = self._resolved_step()
        fault = step.fault_type if injected else None

        record = RecordedRequest(
            url=url,
            method=method,
            headers=headers,
            body=body,
            was_fault_injected=injected,
            injected_fault=fault,
        )
        self._recorded_requests.append(record)
        self.advance_step()
        return record

    @property
    def total_attempts(self) -> int:
        return self._attempts

    @property
    def recorded_requests(self) -> list[RecordedRequest]:
        return list(self._recorded_requests)

    def get_delay(self) -> float:
        """Returns the delay in seconds configured for the active step."""
        return self._resolved_step().delay_seconds

    @property
    def fault(self) -> FaultType:
        """Convenience property for active step fault type."""
        return self._resolved_step().fault_type

    @property
    def status_code(self) -> int | None:
        """Convenience property for active step status code."""
        return self._resolved_step().status_code

    @property
    def retry_after_seconds(self) -> int:
        """Convenience property for active step retry-after."""
        return self._resolved_step().retry_after_seconds

    @property
    def custom_headers(self) -> dict[str, str]:
        """Convenience property for active step headers."""
        return self._resolved_step().headers

    @property
    def custom_body(self) -> str | None:
        """Convenience property for active step body."""
        return self._resolved_step().body

    def reset(self) -> None:
        """Resets the state machine back to the first step."""
        self._current_step_index = 0
        self._current_step_count = 0
        self._attempts = 0
        self._recorded_requests.clear()
        self._active_evaluated_step = None
