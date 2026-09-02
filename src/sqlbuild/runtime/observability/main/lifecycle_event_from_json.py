"""Lifecycle event JSON decode entrypoint."""

from sqlbuild.runtime.observability._helpers.observability import (
    lifecycle_event_from_json as _lifecycle_event_from_json,
)
from sqlbuild.runtime.observability.models import LifecycleEvent, OpaqueLifecycleEvent


def lifecycle_event_from_json(raw_json: str) -> LifecycleEvent | OpaqueLifecycleEvent:
    """Decode known lifecycle events and retain unknown envelopes opaquely."""

    return _lifecycle_event_from_json(raw_json)
