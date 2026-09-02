"""Canonical lifecycle event content entrypoint."""

from sqlbuild.runtime.execution_history._helpers.canonical_events import (
    canonical_event_content as _canonical_event_content,
)
from sqlbuild.runtime.execution_history.types import CanonicalLifecycleEvent


def canonical_event_content(event: CanonicalLifecycleEvent) -> str:
    """Return deterministic content for lifecycle event idempotency comparison."""

    return _canonical_event_content(event=event)
