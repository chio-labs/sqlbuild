"""Invocation-scoped canonical event index for compatibility output."""

from __future__ import annotations

import threading
from collections import defaultdict, deque
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from pathlib import Path

from sqlbuild.runtime.observability.exceptions import ObservabilityValidationError
from sqlbuild.runtime.observability.models import LifecycleEvent

_RESOURCE_TERMINALS: frozenset[str] = frozenset(
    {"resource_attempt_completed", "resource_attempt_failed"}
)
_RUN_TERMINALS: frozenset[str] = frozenset({"run_completed", "run_failed"})
_INVOCATION_TERMINALS: frozenset[str] = frozenset({"invocation_completed", "invocation_failed"})
_OPERATION_TERMINALS: frozenset[str] = frozenset({"operation_completed", "operation_failed"})
_AGGREGATE_OPERATION_NAMES: frozenset[str] = frozenset(
    {"clone_execution", "scenario_capture", "scenario_execution"}
)


class CompatibilityEventProjector:
    """Retain known canonical facts and correlate legacy result enrichment."""

    def __init__(self) -> None:
        self._lock: threading.RLock = threading.RLock()
        self._output_lock: threading.RLock = threading.RLock()
        self._events: list[LifecycleEvent] = []
        self._seen_event_ids: set[str] = set()
        self._resource_ids_by_name: defaultdict[str, set[str]] = defaultdict(set)
        self._pending_by_resource_id: defaultdict[str, deque[LifecycleEvent]] = defaultdict(deque)
        self._claimed_attempt_ids: set[str] = set()
        self._v1_enrichment_by_event_id: dict[str, str] = {}
        self._v1_emitted_event_ids: set[str] = set()
        self._writer_count: int = 0
        self._writer_path: Path | None = None

    def consume(self, event: LifecycleEvent) -> None:
        """Store a known fact once in dispatcher publication order."""

        with self._lock:
            if event.event_id in self._seen_event_ids:
                return
            self._seen_event_ids.add(event.event_id)
            self._events.append(event)
            if event.event_type not in _RESOURCE_TERMINALS:
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
    ) -> LifecycleEvent | None:
        """Claim one matching terminal for a streaming v1 enrichment callback."""

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
            self._claimed_attempt_ids.add(target.resource_attempt_id)
            return target

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
                elif event.event_type in _RESOURCE_TERMINALS:
                    resource = event
                    if event.event_type.endswith("failed"):
                        failed_resource = event
            return invocation or run or operation or failed_resource or resource

    def project_v1(self, *, terminal: LifecycleEvent, payload: str) -> str:
        """Release enriched v1 rows in canonical resource-terminal order."""

        with self._lock:
            self._v1_enrichment_by_event_id[terminal.event_id] = payload
            return self._drain_v1(finalize=False)

    def finalize_v1(self) -> str:
        """Omit unclaimed terminals and release all claimed v1 enrichment in order."""

        with self._lock:
            return self._drain_v1(finalize=True)

    def register_writer(self, *, path: Path | None) -> None:
        """Register one writer and enforce one compatibility side-channel path."""

        with self._lock:
            if self._writer_count and path != self._writer_path:
                raise ObservabilityValidationError(
                    "compatibility event writers must share one output path"
                )
            self._writer_path = path
            self._writer_count += 1

    @contextmanager
    def output_serialization_scope(self) -> Iterator[None]:
        """Serialize projection state transitions with physical compatibility output."""

        with self._output_lock:
            yield

    def unregister_writer(self) -> str:
        """Unregister one writer and finalize only after the last writer closes."""

        with self._lock:
            if self._writer_count == 0:
                return ""
            self._writer_count -= 1
            if self._writer_count:
                return ""
            self._writer_path = None
            return self._drain_v1(finalize=True)

    def events(self) -> tuple[LifecycleEvent, ...]:
        """Return the idempotent canonical facts in publication order."""

        with self._lock:
            return tuple(self._events)

    def _single_resource_id(self, *, resource_name: str) -> str | None:
        resource_ids: set[str] = self._resource_ids_by_name[resource_name]
        if len(resource_ids) != 1:
            return None
        return next(iter(resource_ids))

    def _drain_v1(self, *, finalize: bool) -> str:
        projected: list[str] = []
        terminals: list[LifecycleEvent] = [
            event for event in self._events if event.event_type in _RESOURCE_TERMINALS
        ]
        for event in terminals:
            if event.event_id in self._v1_emitted_event_ids:
                continue
            enrichment: str | None = self._v1_enrichment_by_event_id.get(event.event_id)
            if enrichment is not None:
                projected.append(enrichment)
                self._v1_emitted_event_ids.add(event.event_id)
                continue
            attempt_id: str | None = event.resource_attempt_id
            claimed: bool = attempt_id is not None and attempt_id in self._claimed_attempt_ids
            if finalize and not claimed:
                self._v1_emitted_event_ids.add(event.event_id)
                continue
            if _has_later_enriched_attempt(
                event=event, terminals=terminals, enriched=self._v1_enrichment_by_event_id
            ):
                self._v1_emitted_event_ids.add(event.event_id)
                continue
            break
        return "".join(projected)


_CURRENT_PROJECTOR: ContextVar[CompatibilityEventProjector | None] = ContextVar(
    "sqlbuild_compatibility_event_projector", default=None
)


def current_compatibility_event_projector() -> CompatibilityEventProjector | None:
    """Return the compatibility projector installed for this invocation."""

    return _CURRENT_PROJECTOR.get()


@contextmanager
def compatibility_event_projector_scope(
    projector: CompatibilityEventProjector,
) -> Iterator[CompatibilityEventProjector]:
    """Install and reliably restore one invocation compatibility projector."""

    token: Token[CompatibilityEventProjector | None] = _CURRENT_PROJECTOR.set(projector)
    try:
        yield projector
    finally:
        _CURRENT_PROJECTOR.reset(token)


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


def _has_later_enriched_attempt(
    *,
    event: LifecycleEvent,
    terminals: list[LifecycleEvent],
    enriched: dict[str, str],
) -> bool:
    event_index: int = next(
        index for index, candidate in enumerate(terminals) if candidate is event
    )
    return any(
        candidate.resource_id == event.resource_id and candidate.event_id in enriched
        for candidate in terminals[event_index + 1 :]
    )
