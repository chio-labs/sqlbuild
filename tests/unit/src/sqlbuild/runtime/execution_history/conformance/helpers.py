"""Branch-free canonical event builders for backend conformance tests."""

import json
from datetime import UTC, datetime

from sqlbuild.runtime.observability.main.lifecycle_event_to_json import lifecycle_event_to_json
from sqlbuild.runtime.observability.models import LifecycleEvent, OpaqueLifecycleEvent
from sqlbuild.runtime.observability.types import JSONValue

BASE_TIME: datetime = datetime(2026, 1, 1, tzinfo=UTC)


def lifecycle_event(
    event_id: str,
    event_type: str = "run_started",
    *,
    invocation_id: str = "invocation-1",
    run_id: str | None = "run-1",
    producer: str = "sqlbuild",
    occurred_at: datetime = BASE_TIME,
) -> LifecycleEvent:
    """Build a canonical run lifecycle event for contract tests."""

    return LifecycleEvent(
        event_id=event_id,
        event_type=event_type,
        schema_version=1,
        producer=producer,
        producer_version="0.72.2",
        occurred_at=occurred_at,
        invocation_id=invocation_id,
        run_id=run_id,
        payload={},
    )


def invocation_event(event_id: str) -> LifecycleEvent:
    """Build a canonical invocation event for contract tests."""

    return LifecycleEvent(
        event_id=event_id,
        event_type="invocation_started",
        schema_version=1,
        producer="sqlbuild",
        producer_version="0.72.2",
        occurred_at=BASE_TIME,
        invocation_id="invocation-1",
        payload={"command": "build"},
    )


def opaque_event(
    event_id: JSONValue,
    *,
    event_type: JSONValue = "run_started",
    producer: JSONValue = "opaque-producer",
    invocation_id: JSONValue = "opaque-invocation",
    run_id: JSONValue = "opaque-run",
    occurred_at: JSONValue = "2026-01-01T00:00:00Z",
) -> OpaqueLifecycleEvent:
    """Build an opaque envelope with configurable stable fields."""

    return OpaqueLifecycleEvent(
        raw={
            "event_id": event_id,
            "event_type": event_type,
            "schema_version": 2,
            "producer": producer,
            "occurred_at": occurred_at,
            "invocation_id": invocation_id,
            "run_id": run_id,
        }
    )


def opaque_from_known(event: LifecycleEvent) -> OpaqueLifecycleEvent:
    """Represent known canonical content through the opaque envelope type."""

    raw: object = json.loads(lifecycle_event_to_json(event))
    return OpaqueLifecycleEvent(raw=raw)
