"""Canonical lifecycle event ID entrypoint."""

from sqlbuild.runtime.execution_history._helpers.canonical_events import (
    canonical_event_id as _canonical_event_id,
)
from sqlbuild.runtime.execution_history.types import CanonicalLifecycleEvent


def canonical_event_id(event: CanonicalLifecycleEvent) -> str:
    """Return the required stable ID from a known or opaque lifecycle event."""

    return _canonical_event_id(event=event)
