"""Public state operation/event recording surface."""

from __future__ import annotations

from typing import Any

from sqlbuild.virtual.state._helpers.events import event_id
from sqlbuild.virtual.state.classes.state_backend import StateBackend
from sqlbuild.virtual.state.models import StateOperationEventRecord, StateOperationRecord
from sqlbuild.virtual.state.types import StateOperationStatus, StateOperationType


def record_state_operation(
    *,
    backend: StateBackend,
    connection: Any,
    schema: str,
    operation_id: str,
    operation_type: StateOperationType | None,
    status: StateOperationStatus,
    action: str,
    virtual_environment_name: str | None,
    message: str | None = None,
) -> None:
    """Persist the latest state-operation status plus an append-only event."""

    existing: StateOperationRecord | None = backend.get_state_operation(
        connection=connection,
        schema=schema,
        operation_id=operation_id,
    )
    effective_type: StateOperationType | None = (
        operation_type
        if operation_type is not None
        else (existing.operation_type if existing else None)
    )
    effective_virtual_environment_name: str | None = (
        virtual_environment_name
        if virtual_environment_name is not None
        else (existing.virtual_environment_name if existing else None)
    )
    if effective_type is None:
        return
    backend.upsert_state_operation(
        connection=connection,
        schema=schema,
        record=StateOperationRecord(
            operation_id=operation_id,
            operation_type=effective_type,
            status=status,
            virtual_environment_name=effective_virtual_environment_name,
        ),
    )
    backend.create_state_operation_event(
        connection=connection,
        schema=schema,
        record=StateOperationEventRecord(
            event_id=event_id(),
            operation_id=operation_id,
            action=action,
            status=status,
            message=message,
        ),
    )
