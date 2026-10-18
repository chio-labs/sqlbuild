"""A per-item deadline shared by the executing thread and its expiry watchdog."""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from typing import Any

from sqlbuild.runtime.execution_limits._helpers.cancellation import cancel_connection
from sqlbuild.runtime.execution_limits.classes.active_connections import ActiveConnections
from sqlbuild.runtime.execution_limits.constants import (
    EXPIRY_REPORT_WAIT_SECONDS,
    OUTCOME_SEVERITY,
    SERVER_LIMIT_TOLERANCE_SECONDS,
    WATCHDOG_MAXIMUM_POLL_SECONDS,
    WATCHDOG_MINIMUM_POLL_SECONDS,
)
from sqlbuild.runtime.execution_limits.exceptions import ItemTimeoutError
from sqlbuild.runtime.execution_limits.models import ItemTimeoutPolicy, ItemTimeoutReport
from sqlbuild.runtime.execution_limits.types import CancellationOutcome, ItemKind


class ItemDeadline:
    """One test, scenario or model attempt's running-time budget and its cancellation."""

    def __init__(
        self,
        *,
        kind: ItemKind,
        name: str,
        policy: ItemTimeoutPolicy,
        parent: ItemDeadline | None,
        backstop_grace_seconds: float,
        fallback: tuple[Any, Any],
    ) -> None:
        self.kind: ItemKind = kind
        self.name: str = name
        self.policy: ItemTimeoutPolicy = policy
        self.parent: ItemDeadline | None = parent
        self.expired: bool = False
        self.connections: ActiveConnections = ActiveConnections()
        self._grace: float = backstop_grace_seconds
        self._fallback: tuple[Any, Any] = fallback
        self._spent: float = 0.0
        self._running_since: float | None = None
        self._clock_started: bool = False
        self._holds: int = 0
        self._queued_statements: int = 0
        self._closed: bool = False
        self._active_statements: int = 0
        self._awaiting_confirmation: bool = False
        self._cancellation: CancellationOutcome | None = None
        self._cancellation_detail: str | None = None
        self._query_ids: list[str] = []
        self._lock: threading.RLock = threading.RLock()
        self._expiring: threading.Lock = threading.Lock()
        self._stop: threading.Event = threading.Event()
        self._watchdog: threading.Thread | None = None

    def chain(self) -> Iterator[ItemDeadline]:
        """This deadline and every enclosing one, innermost first."""

        deadline: ItemDeadline | None = self
        while deadline is not None:
            yield deadline
            deadline = deadline.parent

    @property
    def remaining_seconds(self) -> float:
        """Running time left before the earliest limit in the chain, ignoring backstop grace."""

        return max(0.0, min(deadline._own_remaining(grace=0.0) for deadline in self.chain()))

    def running_seconds(self) -> float:
        with self._lock:
            running: float = self._spent
            if self._running_since is not None:
                running += time.monotonic() - self._running_since
            return running

    def enforce(self) -> None:
        """Refuse new work once any deadline in the chain is past its limit and grace."""

        for deadline in self.chain():
            deadline._raise_when_past(grace=deadline._grace)

    def enforce_after_failure(self) -> None:
        """Treat a failed statement as a timeout once its running time reached a limit."""

        for deadline in self.chain():
            deadline._raise_when_past(grace=-SERVER_LIMIT_TOLERANCE_SECONDS)

    def statement_started(self) -> None:
        """Count a statement; the first one starts the running-time clock and the watchdog."""

        for deadline in self.chain():
            deadline._start_statement()

    def statement_finished(self, *, query_id: str | None) -> None:
        for deadline in self.chain():
            with deadline._lock:
                deadline._active_statements = max(0, deadline._active_statements - 1)
                if query_id:
                    deadline._query_ids.append(query_id)
                deadline._update_clock()

    def statement_submitted(self, *, query_id: str | None) -> None:
        if not query_id:
            return
        for deadline in self.chain():
            with deadline._lock:
                deadline._query_ids.append(query_id)

    def hold(self) -> None:
        """Stop the clock for cleanup while no statement runs under this deadline."""

        for deadline in self.chain():
            with deadline._lock:
                deadline._holds += 1
                deadline._update_clock()

    def release(self) -> None:
        for deadline in self.chain():
            with deadline._lock:
                deadline._holds = max(0, deadline._holds - 1)
                deadline._update_clock()

    def statement_queued(self) -> None:
        """Mark a running statement as waiting in a warehouse queue; only queued work pauses."""

        for deadline in self.chain():
            with deadline._lock:
                deadline._queued_statements += 1
                deadline._update_clock()

    def statement_dequeued(self) -> None:
        for deadline in self.chain():
            with deadline._lock:
                deadline._queued_statements = max(0, deadline._queued_statements - 1)
                deadline._update_clock()

    def close(self) -> None:
        """Stop the clock and the watchdog when the item's scope ends."""

        with self._lock:
            self._closed = True
            self._pause_clock()
        self._stop.set()

    def expire(self) -> None:
        """Mark the deadline expired and cancel every statement still running under it."""

        with self._expiring:
            self.expired = True
            outcomes: list[tuple[CancellationOutcome, str | None]] = (
                self.connections.cancel_running(
                    cancel=lambda adapter, connection: cancel_connection(
                        adapter=adapter, connection=connection
                    )
                )
            )
            with self._lock:
                if not outcomes and self._active_statements:
                    adapter, connection = self._fallback
                    outcomes = [cancel_connection(adapter=adapter, connection=connection)]
                if not outcomes:
                    return
                outcome: CancellationOutcome = CancellationOutcome.CONFIRMED
                details: list[str] = []
                for target_outcome, detail in outcomes:
                    if OUTCOME_SEVERITY[target_outcome] > OUTCOME_SEVERITY[outcome]:
                        outcome = target_outcome
                    if detail is not None and detail not in details:
                        details.append(detail)
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
                elapsed_seconds=self.running_seconds(),
                query_ids=tuple(dict.fromkeys(self._query_ids)),
                cancellation=outcome,
                cancellation_detail=self._cancellation_detail,
            )

    def _own_remaining(self, *, grace: float) -> float:
        return self.policy.seconds + grace - self.running_seconds()

    def _raise_when_past(self, *, grace: float) -> None:
        if not self.expired and (not self._clock_started or self._own_remaining(grace=grace) > 0):
            return
        self.expired = True
        raise ItemTimeoutError(kind=self.kind, name=self.name, limit=self.policy.limit)

    def _start_statement(self) -> None:
        with self._lock:
            self._active_statements += 1
            if self._clock_started or self._closed:
                self._update_clock()
                return
            self._clock_started = True
            self._resume_clock()
            self._watchdog = threading.Thread(
                target=self._watch, name=f"sqlbuild-deadline-{self.name}", daemon=True
            )
            self._watchdog.start()

    def _pause_clock(self) -> None:
        if self._running_since is not None:
            self._spent += time.monotonic() - self._running_since
            self._running_since = None

    def _resume_clock(self) -> None:
        if self._clock_started and not self._closed and not self._paused():
            self._running_since = self._running_since or time.monotonic()

    def _paused(self) -> bool:
        """Paused while held or queued, unless another statement is running meanwhile."""

        held: bool = bool(self._holds or self._queued_statements)
        return held and self._active_statements <= self._queued_statements

    def _update_clock(self) -> None:
        if self._paused():
            self._pause_clock()
        else:
            self._resume_clock()

    def _watch(self) -> None:
        while True:
            remaining: float = self._own_remaining(grace=self._grace)
            if remaining <= 0:
                self.expire()
                return
            poll: float = min(
                WATCHDOG_MAXIMUM_POLL_SECONDS, max(WATCHDOG_MINIMUM_POLL_SECONDS, remaining)
            )
            if self._stop.wait(timeout=poll):
                return
