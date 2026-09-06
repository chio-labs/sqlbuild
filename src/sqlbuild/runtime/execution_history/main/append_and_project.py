"""Durable append and rebuildable projection orchestration."""

from collections.abc import Iterable

from sqlbuild.runtime.execution_history.models import StoredEvent
from sqlbuild.runtime.execution_history.types import (
    CanonicalLifecycleEvent,
    LifecycleEventLogStorage,
    RunStorage,
)


def append_and_project(
    *,
    event_log: LifecycleEventLogStorage,
    run_storage: RunStorage,
    events: Iterable[CanonicalLifecycleEvent],
) -> tuple[StoredEvent, ...]:
    """Append facts durably before publishing their rebuildable run projection."""

    stored_events: tuple[StoredEvent, ...] = event_log.append_events(events)
    _ = run_storage.project(stored_events)
    return stored_events
