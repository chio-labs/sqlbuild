from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlbuild.virtual.state.classes.state_backend import StateBackend
from sqlbuild.virtual.state.models import (
    FunctionVersionRecord,
    ModelVersionRecord,
    PhysicalRelationAncestryRecord,
    PhysicalRelationRecord,
    ReconcileEventRecord,
    StateLockRecord,
    StateOperationEventRecord,
    StateOperationRecord,
    StateSchemaValidationResult,
    VirtualEnvironmentCheckpointFunctionRefRecord,
    VirtualEnvironmentCheckpointRecord,
    VirtualEnvironmentCheckpointRefRecord,
    VirtualEnvironmentFunctionRefRecord,
    VirtualEnvironmentRecord,
    VirtualEnvironmentRefRecord,
)
from sqlbuild.virtual.state.types import StateColumnType


def state_type_matches_for_test(actual_type: str, expected_type: StateColumnType) -> bool:
    return actual_type.lower() == expected_type.value or (
        expected_type == StateColumnType.TEXT and actual_type.lower() == "varchar"
    )


def state_columns_for_test(
    expected_columns: dict[str, dict[str, StateColumnType]],
) -> dict[str, dict[str, str]]:
    return {
        table_name: {
            column_name: _state_column_type_for_test(column_type)
            for column_name, column_type in columns.items()
        }
        for table_name, columns in expected_columns.items()
    }


def state_indexes_for_test(
    expected_indexes: dict[str, dict[str, tuple[str, ...]]],
) -> dict[str, set[str]]:
    return {table_name: set(indexes) for table_name, indexes in expected_indexes.items()}


def _state_column_type_for_test(column_type: StateColumnType) -> str:
    if column_type == StateColumnType.TEXT:
        return "VARCHAR"
    return column_type.value.upper()


class FakeStateBackend(StateBackend):
    def __init__(self, *, acquire_result: bool) -> None:
        self.acquire_result: bool = acquire_result
        self.acquire_calls: list[tuple[str, str, datetime]] = []
        self.release_calls: list[tuple[str, str]] = []

    def connect(self, config: dict[str, object]) -> Any:
        return object()

    def close(self, connection: Any) -> None:
        return None

    def initialize(self, connection: Any, *, schema: str, sqlbuild_version: str) -> None:
        return None

    def validate_schema(self, connection: Any, *, schema: str) -> StateSchemaValidationResult:
        return StateSchemaValidationResult()

    def create_backup(self, connection: Any, *, schema: str) -> str:
        return "backup"

    def rollback(self, connection: Any, *, schema: str, backup_id: str | None = None) -> str:
        return backup_id or "backup"

    def reset(self, connection: Any, *, schema: str) -> None:
        return None

    def upsert_model_version(
        self, connection: Any, *, schema: str, record: ModelVersionRecord
    ) -> None:
        return None

    def get_model_version(
        self, connection: Any, *, schema: str, model_name: str, version_hash: str
    ) -> ModelVersionRecord | None:
        return None

    def upsert_function_version(
        self, connection: Any, *, schema: str, record: FunctionVersionRecord
    ) -> None:
        return None

    def get_function_version(
        self, connection: Any, *, schema: str, function_name: str, version_hash: str
    ) -> FunctionVersionRecord | None:
        return None

    def upsert_physical_relation(
        self, connection: Any, *, schema: str, record: PhysicalRelationRecord
    ) -> None:
        return None

    def get_physical_relation(
        self, connection: Any, *, schema: str, model_name: str, version_hash: str
    ) -> PhysicalRelationRecord | None:
        return None

    def list_physical_relations_for_model(
        self, connection: Any, *, schema: str, model_name: str
    ) -> tuple[PhysicalRelationRecord, ...]:
        return ()

    def upsert_physical_relation_ancestry(
        self, connection: Any, *, schema: str, record: PhysicalRelationAncestryRecord
    ) -> None:
        return None

    def get_physical_relation_ancestry(
        self, connection: Any, *, schema: str, model_name: str, version_hash: str
    ) -> PhysicalRelationAncestryRecord | None:
        return None

    def upsert_virtual_environment(
        self, connection: Any, *, schema: str, record: VirtualEnvironmentRecord
    ) -> None:
        return None

    def get_virtual_environment(
        self, connection: Any, *, schema: str, virtual_environment_name: str
    ) -> VirtualEnvironmentRecord | None:
        return None

    def replace_virtual_environment_refs(
        self,
        connection: Any,
        *,
        schema: str,
        virtual_environment_name: str,
        refs: tuple[VirtualEnvironmentRefRecord, ...],
    ) -> None:
        return None

    def get_virtual_environment_refs(
        self, connection: Any, *, schema: str, virtual_environment_name: str
    ) -> tuple[VirtualEnvironmentRefRecord, ...]:
        return ()

    def replace_virtual_environment_function_refs(
        self,
        connection: Any,
        *,
        schema: str,
        virtual_environment_name: str,
        refs: tuple[VirtualEnvironmentFunctionRefRecord, ...],
    ) -> None:
        return None

    def get_virtual_environment_function_refs(
        self, connection: Any, *, schema: str, virtual_environment_name: str
    ) -> tuple[VirtualEnvironmentFunctionRefRecord, ...]:
        return ()

    def create_virtual_environment_checkpoint(
        self,
        connection: Any,
        *,
        schema: str,
        checkpoint: VirtualEnvironmentCheckpointRecord,
        refs: tuple[VirtualEnvironmentCheckpointRefRecord, ...],
        function_refs: tuple[VirtualEnvironmentCheckpointFunctionRefRecord, ...] = (),
    ) -> None:
        return None

    def list_virtual_environment_checkpoints(
        self, connection: Any, *, schema: str, virtual_environment_name: str
    ) -> tuple[VirtualEnvironmentCheckpointRecord, ...]:
        return ()

    def get_virtual_environment_checkpoint_refs(
        self, connection: Any, *, schema: str, checkpoint_id: str
    ) -> tuple[VirtualEnvironmentCheckpointRefRecord, ...]:
        return ()

    def get_virtual_environment_checkpoint_function_refs(
        self, connection: Any, *, schema: str, checkpoint_id: str
    ) -> tuple[VirtualEnvironmentCheckpointFunctionRefRecord, ...]:
        return ()

    def delete_virtual_environment_checkpoint(
        self, connection: Any, *, schema: str, checkpoint_id: str
    ) -> None:
        return None

    def upsert_state_operation(
        self, connection: Any, *, schema: str, record: StateOperationRecord
    ) -> None:
        return None

    def get_state_operation(
        self, connection: Any, *, schema: str, operation_id: str
    ) -> StateOperationRecord | None:
        return None

    def create_state_operation_event(
        self, connection: Any, *, schema: str, record: StateOperationEventRecord
    ) -> None:
        return None

    def create_reconcile_event(
        self, connection: Any, *, schema: str, record: ReconcileEventRecord
    ) -> None:
        return None

    def acquire_lock(
        self,
        connection: Any,
        *,
        schema: str,
        lock_key: str,
        owner_id: str,
        expires_at: datetime,
    ) -> bool:
        self.acquire_calls.append((lock_key, owner_id, expires_at))
        return self.acquire_result

    def release_lock(self, connection: Any, *, schema: str, lock_key: str, owner_id: str) -> bool:
        self.release_calls.append((lock_key, owner_id))
        return True

    def list_active_locks(self, connection: Any, *, schema: str) -> tuple[StateLockRecord, ...]:
        return ()
