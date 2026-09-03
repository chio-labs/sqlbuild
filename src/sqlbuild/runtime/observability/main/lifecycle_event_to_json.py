"""Lifecycle event JSON encode entrypoint."""

from sqlbuild.runtime.observability._helpers.observability import (
    lifecycle_event_to_json as _lifecycle_event_to_json,
)
from sqlbuild.runtime.observability.models import LifecycleEvent, OpaqueLifecycleEvent


def lifecycle_event_to_json(event: LifecycleEvent | OpaqueLifecycleEvent) -> str:
    """Serialize a known or opaque lifecycle event deterministically."""

    return _lifecycle_event_to_json(event)
