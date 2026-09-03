"""Lifecycle event construction from current execution identity."""

from collections.abc import Mapping
from datetime import UTC, datetime
from importlib.metadata import version
from types import MappingProxyType
from uuid import uuid4

from sqlbuild.runtime.observability._helpers.identity import current_execution_identity
from sqlbuild.runtime.observability.constants import CURRENT_LIFECYCLE_EVENT_SCHEMA_VERSION
from sqlbuild.runtime.observability.exceptions import ObservabilityValidationError
from sqlbuild.runtime.observability.models import ExecutionIdentity, LifecycleEvent
from sqlbuild.runtime.observability.types import JSONValue

_DEFAULT_PRODUCER: str = "sqlbuild"


def create_lifecycle_event(
    *,
    event_type: str,
    payload: Mapping[str, JSONValue] = MappingProxyType({}),
    event_id: str | None = None,
    occurred_at: datetime | None = None,
    producer: str = _DEFAULT_PRODUCER,
    producer_version: str | None = None,
) -> LifecycleEvent:
    identity: ExecutionIdentity | None = current_execution_identity()
    if identity is None:
        raise ObservabilityValidationError(
            "cannot create a lifecycle event without an active invocation identity"
        )
    if producer != _DEFAULT_PRODUCER and producer_version is None:
        raise ObservabilityValidationError(
            "producer_version is required when producer is not 'sqlbuild'"
        )
    return LifecycleEvent(
        event_id=uuid4().hex if event_id is None else event_id,
        event_type=event_type,
        schema_version=CURRENT_LIFECYCLE_EVENT_SCHEMA_VERSION,
        producer=producer,
        producer_version=(
            version(_DEFAULT_PRODUCER) if producer_version is None else producer_version
        ),
        occurred_at=datetime.now(UTC) if occurred_at is None else occurred_at,
        invocation_id=identity.invocation_id,
        run_id=identity.run_id,
        resource_id=identity.resource_id,
        resource_attempt_id=identity.resource_attempt_id,
        operation_id=identity.operation_id,
        statement_id=identity.statement_id,
        payload=payload,
    )
