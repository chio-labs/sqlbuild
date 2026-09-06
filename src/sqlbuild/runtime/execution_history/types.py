"""Execution history type declarations and storage protocols."""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum
from types import TracebackType
from typing import TYPE_CHECKING, Protocol, Self

from sqlbuild.runtime.execution_history.constants import DEFAULT_PAGE_LIMIT

if TYPE_CHECKING:
    from sqlbuild.runtime.execution_history.models import (
        EventFilter,
        EventPage,
        RunFilter,
        RunPage,
        RunRecord,
        StoredEvent,
    )
    from sqlbuild.runtime.observability.models import LifecycleEvent, OpaqueLifecycleEvent

type EventCursor = str
type RunCursor = str
type CanonicalLifecycleEvent = LifecycleEvent | OpaqueLifecycleEvent


class EventFamily(StrEnum):
    """Backend-neutral lifecycle event families."""

    INVOCATION = "invocation"
    RUN = "run"
    RESOURCE_ATTEMPT = "resource_attempt"
    OPERATION = "operation"
    STATEMENT = "statement"


class RunStatus(StrEnum):
    """Latest terminal status derivable from durable run facts."""

    UNKNOWN = "unknown"
    COMPLETED = "completed"
    FAILED = "failed"


class LifecycleEventLogStorage(Protocol):
    """Append-only storage for canonical lifecycle events."""

    def append_event(self, event: CanonicalLifecycleEvent) -> StoredEvent: ...

    def append_events(
        self, events: Iterable[CanonicalLifecycleEvent]
    ) -> tuple[StoredEvent, ...]: ...

    def get_events(
        self,
        *,
        event_filter: EventFilter,
        after_cursor: EventCursor | None = None,
        limit: int = DEFAULT_PAGE_LIMIT,
    ) -> EventPage: ...

    def get_schema_version(self) -> int: ...

    def upgrade_schema(self, *, target_version: int | None = None) -> int: ...

    def close(self) -> None: ...

    def dispose(self) -> None: ...

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None: ...


class RunStorage(Protocol):
    """Atomically published rebuildable projection of durable lifecycle events."""

    def get_run(self, run_id: str) -> RunRecord | None: ...

    def get_runs(
        self,
        *,
        run_filter: RunFilter,
        after_cursor: RunCursor | None = None,
        limit: int = DEFAULT_PAGE_LIMIT,
    ) -> RunPage: ...

    def project(self, stored_events: Iterable[StoredEvent]) -> tuple[RunRecord, ...]:
        """Atomically publish all supplied incremental changes or publish none."""

        ...

    def rebuild_from_events(self, stored_events: Iterable[StoredEvent]) -> tuple[RunRecord, ...]:
        """Atomically replace the projection from durable facts or preserve the prior state."""

        ...

    def get_schema_version(self) -> int: ...

    def upgrade_schema(self, *, target_version: int | None = None) -> int: ...

    def close(self) -> None: ...

    def dispose(self) -> None: ...

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None: ...
