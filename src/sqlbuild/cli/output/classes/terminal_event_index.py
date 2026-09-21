"""Invocation-scoped canonical terminal event index."""

from __future__ import annotations

import threading
from collections import defaultdict, deque
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token

from sqlbuild.cli.output.models import TerminalEventClaim
from sqlbuild.runtime.observability.constants import RESOURCE_TERMINALS
from sqlbuild.runtime.observability.models import LifecycleEvent

_RUN_TERMINALS: frozenset[str] = frozenset({"run_completed", "run_failed"})
_INVOCATION_TERMINALS: frozenset[str] = frozenset({"invocation_completed", "invocation_failed"})
_OPERATION_TERMINALS: frozenset[str] = frozenset({"operation_completed", "operation_failed"})
_AGGREGATE_OPERATION_NAMES: frozenset[str] = frozenset(
    {"clone_execution", "scenario_capture", "scenario_execution"}
)


class TerminalEventIndex:
    """Retain canonical facts and claim resource terminals for result projection."""

    def __init__(self) -> None:
        self._lock: threading.RLock = threading.RLock()
        self._output_lock: threading.RLock = threading.RLock()
        self._events: list[LifecycleEvent] = []
        self._event_sequence_by_id: dict[str, int] = {}
        self._seen_event_ids: set[str] = set()
        self._resource_ids_by_name: defaultdict[str, set[str]] = defaultdict(set)
        self._pending_by_resource_id: defaultdict[str, deque[LifecycleEvent]] = defaultdict(deque)
        self._claimed_attempt_ids: set[str] = set()

    def consume(self, event: LifecycleEvent) -> None:
        """Store a known fact once in dispatcher publication order."""

        with self._lock:
            if event.event_id in self._seen_event_ids:
                return
            self._seen_event_ids.add(event.event_id)
            self._event_sequence_by_id[event.event_id] = len(self._events)
            self._events.append(event)
            if event.event_type not in RESOURCE_TERMINALS:
                return
            resource_id: str | None = event.resource_id
            resource_name: object = event.payload.get("resource_name")
            if resource_id is None or not isinstance(resource_name, str):
                return
            self._resource_ids_by_name[resource_name].add(resource_id)
            self._pending_by_resource_id[resource_id].append(event)

    def claim_resource_terminal(
        self,
        *,
        resource_name: str,
        resource_id: str | None = None,
        resource_attempt_id: str | None = None,
        attempt_number: int | None = None,
    ) -> TerminalEventClaim | None:
        """Claim the latest exact terminal available when a result callback arrives."""

        with self._lock:
            resolved_id: str | None = resource_id or self._single_resource_id(
                resource_name=resource_name
            )
            if resolved_id is None:
                return None
            candidates: deque[LifecycleEvent] = self._pending_by_resource_id[resolved_id]
            target: LifecycleEvent | None = _claim_target(
                candidates=candidates,
                resource_attempt_id=resource_attempt_id,
                attempt_number=attempt_number,
                claimed_attempt_ids=self._claimed_attempt_ids,
            )
            if target is None or target.resource_attempt_id is None:
                return None
            self._retire_earlier_attempts(candidates=candidates, target=target)
            self._claimed_attempt_ids.add(target.resource_attempt_id)
            return TerminalEventClaim(
                terminal=target,
                event_sequence=self._event_sequence_by_id[target.event_id],
            )

    def resource_terminal(
        self, *, resource_name: str, resource_id: str | None = None
    ) -> LifecycleEvent | None:
        """Return the latest matching terminal without claiming it."""

        with self._lock:
            resolved_id: str | None = resource_id or self._single_resource_id(
                resource_name=resource_name
            )
            if resolved_id is None:
                return None
            candidates: deque[LifecycleEvent] = self._pending_by_resource_id[resolved_id]
            return candidates[-1] if candidates else None

    def lifecycle_terminal(self) -> LifecycleEvent | None:
        """Return the strongest aggregate terminal available to final JSON."""

        with self._lock:
            invocation: LifecycleEvent | None = None
            run: LifecycleEvent | None = None
            operation: LifecycleEvent | None = None
            resource: LifecycleEvent | None = None
            failed_resource: LifecycleEvent | None = None
            for event in self._events:
                if event.event_type in _INVOCATION_TERMINALS:
                    invocation = event
                elif event.event_type in _RUN_TERMINALS:
                    run = event
                elif (
                    event.event_type in _OPERATION_TERMINALS
                    and event.payload.get("operation_name") in _AGGREGATE_OPERATION_NAMES
                ):
                    operation = event
                elif event.event_type in RESOURCE_TERMINALS:
                    resource = event
                    if event.event_type.endswith("failed"):
                        failed_resource = event
            return invocation or run or operation or failed_resource or resource

    @contextmanager
    def output_serialization_scope(self) -> Iterator[None]:
        """Serialize terminal claims with physical integration-result output."""

        with self._output_lock:
            yield

    def events(self) -> tuple[LifecycleEvent, ...]:
        """Return idempotent canonical facts in publication order."""

        with self._lock:
            return tuple(self._events)

    def _single_resource_id(self, *, resource_name: str) -> str | None:
        resource_ids: set[str] = self._resource_ids_by_name[resource_name]
        if len(resource_ids) != 1:
            return None
        return next(iter(resource_ids))

    def _retire_earlier_attempts(
        self, *, candidates: deque[LifecycleEvent], target: LifecycleEvent
    ) -> None:
        target_sequence: int = self._event_sequence_by_id[target.event_id]
        for event in candidates:
            if self._event_sequence_by_id[event.event_id] >= target_sequence:
                return
            if event.resource_attempt_id is not None:
                self._claimed_attempt_ids.add(event.resource_attempt_id)


_CURRENT_TERMINAL_INDEX: ContextVar[TerminalEventIndex | None] = ContextVar(
    "sqlbuild_terminal_event_index", default=None
)


def current_terminal_event_index() -> TerminalEventIndex | None:
    """Return the terminal event index installed for this invocation."""

    return _CURRENT_TERMINAL_INDEX.get()


@contextmanager
def terminal_event_index_scope(index: TerminalEventIndex) -> Iterator[TerminalEventIndex]:
    """Install and reliably restore one invocation terminal event index."""

    token: Token[TerminalEventIndex | None] = _CURRENT_TERMINAL_INDEX.set(index)
    try:
        yield index
    finally:
        _CURRENT_TERMINAL_INDEX.reset(token)


def _claim_target(
    *,
    candidates: deque[LifecycleEvent],
    resource_attempt_id: str | None,
    attempt_number: int | None,
    claimed_attempt_ids: set[str],
) -> LifecycleEvent | None:
    available: list[LifecycleEvent] = [
        event
        for event in candidates
        if event.resource_attempt_id is not None
        and event.resource_attempt_id not in claimed_attempt_ids
    ]
    if resource_attempt_id is not None:
        return next(
            (event for event in available if event.resource_attempt_id == resource_attempt_id),
            None,
        )
    if attempt_number is not None:
        return next(
            (
                event
                for event in reversed(available)
                if event.payload.get("attempt_number") == attempt_number
            ),
            None,
        )
    return available[-1] if available else None
