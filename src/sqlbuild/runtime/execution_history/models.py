"""Immutable execution history records, filters, and pages."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlbuild._native import (
    validate_history_event_filter,
    validate_history_page,
    validate_history_run_filter,
    validate_stored_history_event,
)
from sqlbuild.runtime.execution_history.types import (
    CanonicalLifecycleEvent,
    EventCursor,
    EventFamily,
    RunCursor,
    RunStatus,
)


@dataclass(frozen=True)
class StoredEvent:
    """One canonical event with backend-assigned durable ordering metadata."""

    storage_order: int
    cursor: EventCursor
    received_at: datetime
    event: CanonicalLifecycleEvent

    def __post_init__(self) -> None:
        validate_stored_history_event(self)


@dataclass(frozen=True)
class EventFilter:
    """Storage-facing lifecycle event selection without presentation concerns."""

    invocation_id: str | None = None
    run_id: str | None = None
    event_types: tuple[str, ...] = ()
    family: EventFamily | None = None
    producer: str | None = None
    occurred_at_start: datetime | None = None
    occurred_at_end: datetime | None = None

    def __post_init__(self) -> None:
        validate_history_event_filter(self)


@dataclass(frozen=True)
class EventPage:
    """Ascending page of durable lifecycle event facts."""

    records: tuple[StoredEvent, ...]
    next_cursor: EventCursor | None
    has_more: bool

    def __post_init__(self) -> None:
        validate_history_page(page=self, is_event_page=True)


@dataclass(frozen=True)
class RunRecord:
    """Run state reproducible solely from durable lifecycle events."""

    run_id: str
    invocation_id: str
    created_at: datetime
    status: RunStatus
    is_complete: bool
    last_event_cursor: EventCursor
    last_storage_order: int
    command: str | None = None
    target: str | None = None
    environment: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None


@dataclass(frozen=True)
class RunFilter:
    """Backend-neutral run projection selection."""

    invocation_id: str | None = None
    statuses: tuple[RunStatus, ...] = ()
    created_at_start: datetime | None = None
    created_at_end: datetime | None = None

    def __post_init__(self) -> None:
        validate_history_run_filter(self)


@dataclass(frozen=True)
class RunPage:
    """Page of runs ordered by the deterministic created-time and run-ID key."""

    records: tuple[RunRecord, ...]
    next_cursor: RunCursor | None
    has_more: bool

    def __post_init__(self) -> None:
        validate_history_page(page=self, is_event_page=False)
