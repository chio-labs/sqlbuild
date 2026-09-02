"""Immutable execution history records, filters, and pages."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlbuild.runtime.execution_history.exceptions import (
    InvalidFilterError,
    ProjectionConsistencyError,
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
        from sqlbuild.runtime.execution_history._helpers.validation import (
            validate_storage_timestamp,
        )

        if self.storage_order < 1:
            raise ProjectionConsistencyError("storage_order must be a positive integer")
        if not self.cursor:
            raise ProjectionConsistencyError("event cursor must be non-empty")
        validate_storage_timestamp(value=self.received_at, field_name="received_at")


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
        from sqlbuild.runtime.execution_history._helpers.validation import (
            validate_filter_text,
            validate_filter_timestamp,
        )

        for field_name in ("invocation_id", "run_id", "producer"):
            validate_filter_text(value=getattr(self, field_name), field_name=field_name)
        if self.event_types and self.family is not None:
            raise InvalidFilterError("event_types and family are mutually exclusive")
        if any(not event_type.strip() for event_type in self.event_types):
            raise InvalidFilterError("event_types must contain only non-empty values")
        for field_name, value in (
            ("occurred_at_start", self.occurred_at_start),
            ("occurred_at_end", self.occurred_at_end),
        ):
            validate_filter_timestamp(value=value, field_name=field_name)
        if (
            self.occurred_at_start is not None
            and self.occurred_at_end is not None
            and self.occurred_at_start > self.occurred_at_end
        ):
            raise InvalidFilterError("occurred_at_start must not be after occurred_at_end")


@dataclass(frozen=True)
class EventPage:
    """Ascending page of durable lifecycle event facts."""

    records: tuple[StoredEvent, ...]
    next_cursor: EventCursor | None
    has_more: bool

    def __post_init__(self) -> None:
        if not self.records and self.next_cursor is not None:
            raise ProjectionConsistencyError("an empty event page cannot have a next cursor")
        if self.records and self.next_cursor != self.records[-1].cursor:
            raise ProjectionConsistencyError("event page cursor must identify its last record")


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
        from sqlbuild.runtime.execution_history._helpers.validation import (
            validate_filter_text,
            validate_filter_timestamp,
        )

        validate_filter_text(value=self.invocation_id, field_name="invocation_id")
        for field_name, value in (
            ("created_at_start", self.created_at_start),
            ("created_at_end", self.created_at_end),
        ):
            validate_filter_timestamp(value=value, field_name=field_name)
        if (
            self.created_at_start is not None
            and self.created_at_end is not None
            and self.created_at_start > self.created_at_end
        ):
            raise InvalidFilterError("created_at_start must not be after created_at_end")


@dataclass(frozen=True)
class RunPage:
    """Page of runs ordered by the deterministic created-time and run-ID key."""

    records: tuple[RunRecord, ...]
    next_cursor: RunCursor | None
    has_more: bool

    def __post_init__(self) -> None:
        if not self.records and self.next_cursor is not None:
            raise ProjectionConsistencyError("an empty run page cannot have a next cursor")
