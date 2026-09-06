"""Typed public execution history API with a deprecated ``EventLogStorage`` alias."""

from collections.abc import Iterable

from sqlbuild.runtime.execution_history.constants import DEFAULT_PAGE_LIMIT, MAX_PAGE_LIMIT
from sqlbuild.runtime.execution_history.exceptions import (
    ExecutionHistoryStorageError,
    IntegrityConflictError,
    InvalidCursorError,
    InvalidEventError,
    InvalidFilterError,
    InvalidLimitError,
    ProjectionConsistencyError,
    UnsupportedSchemaVersionError,
)
from sqlbuild.runtime.execution_history.main.append_and_project import (
    append_and_project as _append_and_project,
)
from sqlbuild.runtime.execution_history.main.canonical_event_content import (
    canonical_event_content as _canonical_event_content,
)
from sqlbuild.runtime.execution_history.main.canonical_event_id import (
    canonical_event_id as _canonical_event_id,
)
from sqlbuild.runtime.execution_history.main.project_runs import project_runs as _project_runs
from sqlbuild.runtime.execution_history.main.validate_page_limit import (
    validate_page_limit as _validate_page_limit,
)
from sqlbuild.runtime.execution_history.models import (
    EventFilter,
    EventPage,
    RunFilter,
    RunPage,
    RunRecord,
    StoredEvent,
)
from sqlbuild.runtime.execution_history.types import (
    CanonicalLifecycleEvent,
    EventCursor,
    EventFamily,
    LifecycleEventLogStorage,
    RunCursor,
    RunStatus,
    RunStorage,
)

EventLogStorage: type[LifecycleEventLogStorage] = LifecycleEventLogStorage

__all__ = (
    "DEFAULT_PAGE_LIMIT",
    "MAX_PAGE_LIMIT",
    "CanonicalLifecycleEvent",
    "EventCursor",
    "EventFamily",
    "EventFilter",
    "EventLogStorage",
    "LifecycleEventLogStorage",
    "EventPage",
    "ExecutionHistoryStorageError",
    "IntegrityConflictError",
    "InvalidCursorError",
    "InvalidEventError",
    "InvalidFilterError",
    "InvalidLimitError",
    "ProjectionConsistencyError",
    "RunCursor",
    "RunFilter",
    "RunPage",
    "RunRecord",
    "RunStatus",
    "RunStorage",
    "StoredEvent",
    "UnsupportedSchemaVersionError",
    "append_and_project",
    "canonical_event_content",
    "canonical_event_id",
    "project_runs",
    "validate_page_limit",
)


def append_and_project(
    *,
    event_log: LifecycleEventLogStorage,
    run_storage: RunStorage,
    events: Iterable[CanonicalLifecycleEvent],
) -> tuple[StoredEvent, ...]:
    """Append facts durably before publishing their rebuildable run projection."""

    return _append_and_project(event_log=event_log, run_storage=run_storage, events=events)


def canonical_event_id(event: CanonicalLifecycleEvent) -> str:
    """Return the required stable ID from a known or opaque lifecycle event."""

    return _canonical_event_id(event)


def canonical_event_content(event: CanonicalLifecycleEvent) -> str:
    """Return deterministic content for lifecycle event idempotency comparison."""

    return _canonical_event_content(event)


def project_runs(
    *, stored_events: Iterable[StoredEvent], current_runs: Iterable[RunRecord] = ()
) -> tuple[RunRecord, ...]:
    """Apply durable event facts in storage order to immutable run projections."""

    return _project_runs(stored_events=stored_events, current_runs=current_runs)


def validate_page_limit(limit: int) -> None:
    """Validate a positive page limit no greater than the public maximum."""

    _validate_page_limit(limit)
