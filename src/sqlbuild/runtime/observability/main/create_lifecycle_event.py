"""Lifecycle event factory entrypoint."""

from collections.abc import Mapping
from datetime import datetime
from types import MappingProxyType

from sqlbuild.runtime.observability._helpers.factory import (
    create_lifecycle_event as _create_lifecycle_event,
)
from sqlbuild.runtime.observability.models import LifecycleEvent
from sqlbuild.runtime.observability.types import JSONValue


def create_lifecycle_event(
    *,
    event_type: str,
    payload: Mapping[str, JSONValue] = MappingProxyType({}),
    event_id: str | None = None,
    occurred_at: datetime | None = None,
    producer: str = "sqlbuild",
    producer_version: str | None = None,
) -> LifecycleEvent:
    """Create a validated lifecycle fact from the active execution identity."""

    return _create_lifecycle_event(
        event_type=event_type,
        payload=payload,
        event_id=event_id,
        occurred_at=occurred_at,
        producer=producer,
        producer_version=producer_version,
    )
