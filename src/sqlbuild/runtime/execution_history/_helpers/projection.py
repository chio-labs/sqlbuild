"""Deterministic run projection from durable event facts."""

from collections.abc import Iterable
from dataclasses import replace
from datetime import datetime

from sqlbuild.runtime.execution_history.constants import (
    RUN_COMPLETED_EVENT_TYPE,
    RUN_FAILED_EVENT_TYPE,
    RUN_STARTED_EVENT_TYPE,
)
from sqlbuild.runtime.execution_history.exceptions import ProjectionConsistencyError
from sqlbuild.runtime.execution_history.models import RunRecord, StoredEvent
from sqlbuild.runtime.execution_history.types import RunStatus
from sqlbuild.runtime.observability.models import LifecycleEvent


def project_runs(
    *, stored_events: Iterable[StoredEvent], current_runs: Iterable[RunRecord] = ()
) -> tuple[RunRecord, ...]:
    """Apply durable events in storage order and return deterministic run projections."""

    projected: dict[str, RunRecord] = {run.run_id: run for run in current_runs}
    ordered_events: tuple[StoredEvent, ...] = _get_unique_ordered_events(
        stored_events=stored_events
    )
    for stored_event in ordered_events:
        event: object = stored_event.event
        if not isinstance(event, LifecycleEvent) or event.run_id is None:
            continue
        existing: RunRecord | None = projected.get(event.run_id)
        if existing is not None and stored_event.storage_order <= existing.last_storage_order:
            continue
        projected[event.run_id] = _apply_run_event(
            stored_event=stored_event, event=event, existing=existing
        )
    return tuple(sorted(projected.values(), key=lambda run: (run.created_at, run.run_id)))


def _get_unique_ordered_events(*, stored_events: Iterable[StoredEvent]) -> tuple[StoredEvent, ...]:
    ordered_events: tuple[StoredEvent, ...] = tuple(
        sorted(stored_events, key=lambda stored_event: stored_event.storage_order)
    )
    unique_events: list[StoredEvent] = []
    for stored_event in ordered_events:
        previous: StoredEvent | None = unique_events[-1] if unique_events else None
        if previous is not None and stored_event.storage_order == previous.storage_order:
            if stored_event == previous:
                continue
            raise ProjectionConsistencyError("storage_order must uniquely identify a durable event")
        unique_events.append(stored_event)
    return tuple(unique_events)


def _apply_run_event(
    *, stored_event: StoredEvent, event: LifecycleEvent, existing: RunRecord | None
) -> RunRecord:
    if existing is not None and existing.invocation_id != event.invocation_id:
        raise ProjectionConsistencyError(
            f"run_id {event.run_id!r} has conflicting invocation correlations"
        )
    if existing is None:
        existing = RunRecord(
            run_id=event.run_id or "",
            invocation_id=event.invocation_id,
            created_at=stored_event.received_at,
            status=RunStatus.UNKNOWN,
            is_complete=False,
            last_event_cursor=stored_event.cursor,
            last_storage_order=stored_event.storage_order,
        )
    started_at: datetime | None = (
        event.occurred_at if event.event_type == RUN_STARTED_EVENT_TYPE else existing.started_at
    )
    status, is_complete, ended_at = _terminal_state(event=event, existing=existing)
    return replace(
        existing,
        status=status,
        is_complete=is_complete,
        started_at=started_at,
        ended_at=ended_at,
        last_event_cursor=stored_event.cursor,
        last_storage_order=stored_event.storage_order,
    )


def _terminal_state(
    *, event: LifecycleEvent, existing: RunRecord
) -> tuple[RunStatus, bool, datetime | None]:
    if event.event_type == RUN_COMPLETED_EVENT_TYPE:
        return RunStatus.COMPLETED, True, event.occurred_at
    if event.event_type == RUN_FAILED_EVENT_TYPE:
        return RunStatus.FAILED, True, event.occurred_at
    return existing.status, existing.is_complete, existing.ended_at
