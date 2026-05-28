from __future__ import annotations

from typing import Any

from sqlbuild.virtual.state.models import StateOperationEventRecord, StateOperationRecord


class RecordingStateBackend:
    def __init__(self) -> None:
        self.operation: StateOperationRecord | None = None
        self.events: list[StateOperationEventRecord] = []

    def get_state_operation(
        self,
        _connection: Any,
        *,
        schema: str,
        operation_id: str,
    ) -> StateOperationRecord | None:
        del schema
        if self.operation is None or self.operation.operation_id != operation_id:
            return None
        return self.operation

    def upsert_state_operation(
        self,
        _connection: Any,
        *,
        schema: str,
        record: StateOperationRecord,
    ) -> None:
        del schema
        self.operation = record

    def create_state_operation_event(
        self,
        _connection: Any,
        *,
        schema: str,
        record: StateOperationEventRecord,
    ) -> None:
        del schema
        self.events.append(record)
