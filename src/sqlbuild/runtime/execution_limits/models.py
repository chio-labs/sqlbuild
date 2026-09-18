"""Runtime execution-limit models."""

from __future__ import annotations

import time
from dataclasses import dataclass

from sqlbuild.runtime.execution_limits.exceptions import ExecutionDurationLimitError


@dataclass(frozen=True)
class ExecutionDeadline:
    """One monotonic build deadline and its user-facing policy context."""

    deadline: float
    target_name: str | None
    max_duration: str
    remediation: str | None = None

    @property
    def remaining_seconds(self) -> float:
        return max(0.0, self.deadline - time.monotonic())

    def enforce(self) -> None:
        if self.remaining_seconds > 0:
            return
        raise ExecutionDurationLimitError(
            target_name=self.target_name,
            max_duration=self.max_duration,
            remediation=self.remediation,
        )
