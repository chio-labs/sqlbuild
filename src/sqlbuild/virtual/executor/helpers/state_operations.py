"""State operation and lease bookkeeping phases for virtual executor runs."""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.virtual.executor.models import StateOperationHandle
from sqlbuild.virtual.state.main.environments.record_operation import record_state_operation
from sqlbuild.virtual.state.main.locks.locks import acquire_virtual_environment_lease
from sqlbuild.virtual.state.models import StateLockLease
from sqlbuild.virtual.state.types import StateOperationStatus, StateOperationType


def create_state_operation_handle(operation_type: StateOperationType) -> StateOperationHandle:
    """Create a unique handle identifying one executor state operation."""

    return StateOperationHandle(
        operation_id=f"{operation_type.value}:{uuid.uuid4()}",
        operation_type=operation_type,
    )


def write_state_operation_started(
    backend: Any,
    state_connection: Any,
    *,
    schema: str,
    handle: StateOperationHandle,
    virtual_environment_name: str,
    message: str,
) -> None:
    """Record the RUNNING start event for one executor state operation."""

    record_state_operation(
        backend,
        state_connection,
        schema=schema,
        operation_id=handle.operation_id,
        operation_type=handle.operation_type,
        status=StateOperationStatus.RUNNING,
        action="start",
        virtual_environment_name=virtual_environment_name,
        message=message,
    )


def write_state_operation_result(
    backend: Any,
    state_connection: Any,
    *,
    schema: str,
    handle: StateOperationHandle,
    status: StateOperationStatus,
    message: str,
) -> None:
    """Record the finish event and final status for one executor state operation."""

    record_state_operation(
        backend,
        state_connection,
        schema=schema,
        operation_id=handle.operation_id,
        operation_type=None,
        status=status,
        action="finish",
        virtual_environment_name=None,
        message=message,
    )


def acquire_virtual_environment_lease_or_raise(
    backend: Any,
    state_connection: Any,
    *,
    schema: str,
    virtual_environment_name: str,
    owner_prefix: str,
    locked_error_code: str,
    ttl: timedelta = timedelta(minutes=10),
) -> StateLockLease:
    """Acquire the environment lease or raise a structured locked error."""

    lease: StateLockLease | None = acquire_virtual_environment_lease(
        backend,
        state_connection,
        schema=schema,
        virtual_environment_name=virtual_environment_name,
        owner_id=f"{owner_prefix}:{uuid.uuid4()}",
        ttl=ttl,
    )
    if lease is None:
        raise PlannerInputError(
            f"virtual environment '{virtual_environment_name}' is locked",
            code=locked_error_code,
        )
    return lease
