"""Runtime execution-limit models."""

from __future__ import annotations

import time
from dataclasses import dataclass

from sqlbuild.runtime.execution_limits.exceptions import ExecutionDurationLimitError
from sqlbuild.runtime.execution_limits.types import CancellationOutcome, ItemKind


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


@dataclass(frozen=True)
class ItemTimeoutPolicy:
    """The resolved time limit of one test, scenario or model attempt and where it came from."""

    limit: str
    seconds: int
    source: str


@dataclass(frozen=True)
class RunItemTimeouts:
    """A run's per-item limit, and whether it overrides limits the items declare."""

    timeout_limit: str | None = None
    timeout_seconds: int | None = None
    timeout_source: str | None = None
    timeout_overrides_items: bool = False

    def resolve(
        self, *, declared: str | None, declared_seconds: int | None, declared_source: str
    ) -> ItemTimeoutPolicy | None:
        """The CLI limit, else the item's declared limit, else the run's configured limit."""

        if not self.timeout_overrides_items and declared is not None:
            if declared_seconds is None:
                return None
            return ItemTimeoutPolicy(
                limit=declared, seconds=declared_seconds, source=declared_source
            )
        if self.timeout_limit is None or self.timeout_seconds is None:
            return None
        return ItemTimeoutPolicy(
            limit=self.timeout_limit,
            seconds=self.timeout_seconds,
            source=self.timeout_source or "run settings",
        )


@dataclass(frozen=True)
class ItemTimeoutReport:
    """What happened when one item ran out of time."""

    kind: ItemKind
    name: str
    limit: str
    source: str
    elapsed_seconds: float
    query_ids: tuple[str, ...]
    cancellation: CancellationOutcome
    cancellation_detail: str | None
