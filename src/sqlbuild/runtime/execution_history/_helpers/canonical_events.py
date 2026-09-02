"""Canonical lifecycle event identity and content helpers."""

from sqlbuild.runtime.execution_history.exceptions import InvalidEventError
from sqlbuild.runtime.execution_history.types import CanonicalLifecycleEvent
from sqlbuild.runtime.observability.main.lifecycle_event_to_json import lifecycle_event_to_json
from sqlbuild.runtime.observability.models import LifecycleEvent


def canonical_event_id(*, event: CanonicalLifecycleEvent) -> str:
    """Return the required stable event ID from a known or opaque envelope."""

    event_id: object = (
        event.event_id if isinstance(event, LifecycleEvent) else event.raw.get("event_id")
    )
    if not isinstance(event_id, str) or not event_id:
        raise InvalidEventError("canonical lifecycle event requires a non-empty string event_id")
    return event_id


def canonical_event_content(*, event: CanonicalLifecycleEvent) -> str:
    """Return deterministic canonical content for idempotency comparisons."""

    _ = canonical_event_id(event=event)
    return lifecycle_event_to_json(event)
