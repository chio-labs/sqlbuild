"""A per-item deadline shared by the executing thread and its expiry watchdog."""

from __future__ import annotations

import threading
import time
from typing import Any

from sqlbuild.runtime.execution_limits._helpers.cancellation import cancel_connection
from sqlbuild.runtime.execution_limits.classes.active_connections import ActiveConnections
from sqlbuild.runtime.execution_limits.constants import (
    EXPIRY_REPORT_WAIT_SECONDS,
    OUTCOME_SEVERITY,
)
from sqlbuild.runtime.execution_limits.exceptions import ItemTimeoutError
from sqlbuild.runtime.execution_limits.models import ItemTimeoutPolicy, ItemTimeoutReport
from sqlbuild.runtime.execution_limits.types import CancellationOutcome, ItemKind


class ItemDeadline:
    """One test, scenario or model attempt's deadline, its statements and its cancellation."""

    def __init__(self, *, kind: ItemKind, name: str, policy: ItemTimeoutPolicy) -> None:
        self.kind: ItemKind = kind
        self.name: str = name
        self.policy: ItemTimeoutPolicy = policy
        self.started: float = time.monotonic()
        self.deadline: float = self.started + policy.seconds
        self.expired: bool = False
        self.connections: ActiveConnections = ActiveConnections()
        self._active_statements: int = 0
        self._awaiting_confirmation: bool = False
        self._cancellation: CancellationOutcome | None = None
        self._cancellation_detail: str | None = None
        self._query_ids: list[str] = []
        self._lock: threading.Lock = threading.Lock()
        self._expiring: threading.Lock = threading.Lock()

    @property
    def remaining_seconds(self) -> float:
        return max(0.0, self.deadline - time.monotonic())

    def enforce(self) -> None:
        if not self.expired and self.remaining_seconds > 0:
            return
        self.expired = True
        raise ItemTimeoutError(kind=self.kind, name=self.name, limit=self.policy.limit)

    def statement_started(self) -> None:
        with self._lock:
            self._active_statements += 1

    def statement_finished(self, *, query_id: str | None) -> None:
        with self._lock:
            self._active_statements = max(0, self._active_statements - 1)
            if query_id:
                self._query_ids.append(query_id)

    def statement_submitted(self, *, query_id: str | None) -> None:
        if not query_id:
            return
        with self._lock:
            self._query_ids.append(query_id)

    def expire(self, *, fallback: tuple[Any, Any]) -> None:
        """Mark the deadline expired and cancel every statement still running under it."""

        with self._expiring:
            self._cancel_running(fallback=fallback)

    def _cancel_running(self, *, fallback: tuple[Any, Any]) -> None:
        targets: list[tuple[Any, Any]] = self.connections.snapshot()
        with self._lock:
            self.expired = True
            if not targets and self._active_statements:
                targets = [fallback]
        if not targets:
            return
        outcome: CancellationOutcome = CancellationOutcome.CONFIRMED
        details: list[str] = []
        for adapter, connection in targets:
            target_outcome, detail = cancel_connection(adapter=adapter, connection=connection)
            if OUTCOME_SEVERITY[target_outcome] > OUTCOME_SEVERITY[outcome]:
                outcome = target_outcome
            if detail is not None and detail not in details:
                details.append(detail)
        with self._lock:
            self._cancellation = outcome
            self._awaiting_confirmation = outcome == CancellationOutcome.CONFIRMED
            self._cancellation_detail = "; ".join(details) or None

    def report(self) -> ItemTimeoutReport:
        """What happened at expiry, once any cancellation in progress has finished."""

        if self._expiring.acquire(timeout=EXPIRY_REPORT_WAIT_SECONDS):
            self._expiring.release()
        with self._lock:
            outcome: CancellationOutcome = self._cancellation or CancellationOutcome.NOT_NEEDED
            if self._awaiting_confirmation:
                outcome = (
                    CancellationOutcome.UNKNOWN
                    if self._active_statements
                    else CancellationOutcome.CONFIRMED
                )
            return ItemTimeoutReport(
                kind=self.kind,
                name=self.name,
                limit=self.policy.limit,
                source=self.policy.source,
                elapsed_seconds=max(0.0, time.monotonic() - self.started),
                query_ids=tuple(dict.fromkeys(self._query_ids)),
                cancellation=outcome,
                cancellation_detail=self._cancellation_detail,
            )
