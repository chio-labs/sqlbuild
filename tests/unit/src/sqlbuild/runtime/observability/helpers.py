"""Test builders for runtime observability contracts."""

from collections.abc import Mapping
from datetime import UTC, datetime
from types import MappingProxyType

from sqlbuild.runtime.observability.models import LifecycleEvent
from sqlbuild.runtime.observability.types import JSONValue

OCCURRED_AT: datetime = datetime(2026, 8, 31, 12, 34, 56, 123456, tzinfo=UTC)


def lifecycle_event(
    event_type: str = "invocation_started",
    *,
    run_id: str | None = None,
    resource_id: str | None = None,
    resource_attempt_id: str | None = None,
    operation_id: str | None = None,
    statement_id: str | None = None,
    occurred_at: datetime = OCCURRED_AT,
    payload: Mapping[str, JSONValue] = MappingProxyType({}),
) -> LifecycleEvent:
    """Build a valid known lifecycle event with deterministic values."""

    return LifecycleEvent(
        event_id="evt-1",
        event_type=event_type,
        schema_version=1,
        producer="sqlbuild",
        producer_version="0.72.1",
        occurred_at=occurred_at,
        invocation_id="inv-1",
        run_id=run_id,
        resource_id=resource_id,
        resource_attempt_id=resource_attempt_id,
        operation_id=operation_id,
        statement_id=statement_id,
        payload=payload,
    )
