from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlbuild.executor.node_results.models import NodeResultEnvelope, NodeResultRecord
from sqlbuild.virtual.state.classes.state_backend import StateBackend
from sqlbuild.virtual.state.models import (
    FunctionVersionRecord,
    ModelVersionRecord,
    PhysicalRelationAncestryRecord,
    PhysicalRelationRecord,
    PythonNodeVersionRecord,
    ReconcileEventRecord,
    SeedVersionRecord,
    SourceFreshnessRecord,
    StateBackupRecord,
    StateLockRecord,
    StateOperationEventRecord,
    StateOperationRecord,
    StateSchemaValidationResult,
    VirtualEnvironmentCheckpointFunctionRefRecord,
    VirtualEnvironmentCheckpointModelRefRecord,
    VirtualEnvironmentCheckpointRecord,
    VirtualEnvironmentCheckpointSeedRefRecord,
    VirtualEnvironmentFunctionRefRecord,
    VirtualEnvironmentModelRefRecord,
    VirtualEnvironmentNodeRefRecord,
    VirtualEnvironmentPythonNodeRefRecord,
    VirtualEnvironmentRecord,
    VirtualEnvironmentRetentionRecord,
    VirtualEnvironmentSeedRefRecord,
)
from sqlbuild.virtual.state.types import PhysicalArtifactType, StateColumnType


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


def virtual_environment_ref_for_test(
    virtual_environment_name: str, model_name: str, version_hash: str
) -> VirtualEnvironmentModelRefRecord:
    return VirtualEnvironmentModelRefRecord(
        virtual_environment_name=virtual_environment_name,
        model_name=model_name,
        version_hash=version_hash,
    )


def physical_relation_for_test(relation_name: str, version_hash: str) -> PhysicalRelationRecord:
    return PhysicalRelationRecord(
        artifact_type=PhysicalArtifactType.MODEL,
        artifact_name="orders",
        version_hash=version_hash,
        database_name=None,
        schema_name="dev__sqb_physical",
        relation_name=relation_name,
        relation_type="table",
    )


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

    def upsert_seed_version(
        self, connection: Any, *, schema: str, record: SeedVersionRecord
    ) -> None:
        return None

    def get_seed_version(
        self, connection: Any, *, schema: str, seed_name: str, version_hash: str
    ) -> SeedVersionRecord | None:
        return None

    def upsert_python_node_version(
        self, connection: Any, *, schema: str, record: PythonNodeVersionRecord
    ) -> None:
        return None

    def get_python_node_version(
        self,
        connection: Any,
        *,
        schema: str,
        node_type: str,
        node_name: str,
        version_hash: str,
    ) -> PythonNodeVersionRecord | None:
        return None

    def insert_node_result(
        self,
        connection: Any,
        *,
        schema: str,
        virtual_environment_name: str,
        record: NodeResultRecord,
    ) -> None:
        return None

    def read_node_results(
        self,
        connection: Any,
        *,
        schema: str,
        virtual_environment_name: str,
        node_type: str,
        node_name: str,
        target_database: str | None,
        target_schema: str | None,
        target_name: str | None,
        statuses: tuple[str, ...] | None,
        run_id: str | None,
        limit: int,
    ) -> tuple[NodeResultEnvelope, ...]:
        return ()

    def upsert_physical_relation(
        self, connection: Any, *, schema: str, record: PhysicalRelationRecord
    ) -> None:
        return None

    def get_physical_relation_for_artifact(
        self,
        connection: Any,
        *,
        schema: str,
        artifact_type: PhysicalArtifactType,
        artifact_name: str,
        version_hash: str,
    ) -> PhysicalRelationRecord | None:
        return None

    def list_physical_relations_for_artifact(
        self,
        connection: Any,
        *,
        schema: str,
        artifact_type: PhysicalArtifactType,
        artifact_name: str,
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

    def list_virtual_environments(
        self, connection: Any, *, schema: str
    ) -> tuple[VirtualEnvironmentRetentionRecord, ...]:
        return ()

    def delete_virtual_environment(
        self, connection: Any, *, schema: str, virtual_environment_name: str
    ) -> None:
        return None

    def replace_virtual_environment_node_refs(
        self,
        connection: Any,
        *,
        schema: str,
        virtual_environment_name: str,
        node_type: str,
        refs: tuple[VirtualEnvironmentNodeRefRecord, ...],
    ) -> None:
        return None

    def get_virtual_environment_node_refs(
        self,
        connection: Any,
        *,
        schema: str,
        virtual_environment_name: str,
        node_type: str,
    ) -> tuple[VirtualEnvironmentNodeRefRecord, ...]:
        return ()

    def replace_virtual_environment_node_ref_groups(
        self,
        connection: Any,
        *,
        schema: str,
        virtual_environment_name: str,
        refs_by_node_type: dict[str, tuple[VirtualEnvironmentNodeRefRecord, ...]],
    ) -> None:
        return None

    def upsert_virtual_environment_and_replace_node_ref_groups(
        self,
        connection: Any,
        *,
        schema: str,
        record: VirtualEnvironmentRecord,
        refs_by_node_type: dict[str, tuple[VirtualEnvironmentNodeRefRecord, ...]],
    ) -> None:
        return None

    def upsert_virtual_environment_node_ref(
        self,
        connection: Any,
        *,
        schema: str,
        ref: VirtualEnvironmentNodeRefRecord,
    ) -> None:
        return None

    def replace_virtual_environment_model_refs(
        self,
        connection: Any,
        *,
        schema: str,
        virtual_environment_name: str,
        refs: tuple[VirtualEnvironmentModelRefRecord, ...],
    ) -> None:
        return None

    def get_virtual_environment_model_refs(
        self, connection: Any, *, schema: str, virtual_environment_name: str
    ) -> tuple[VirtualEnvironmentModelRefRecord, ...]:
        return ()

    def replace_virtual_environment_source_freshness(
        self,
        connection: Any,
        *,
        schema: str,
        virtual_environment_name: str,
        records: tuple[SourceFreshnessRecord, ...],
    ) -> None:
        return None

    def get_virtual_environment_source_freshness(
        self, connection: Any, *, schema: str, virtual_environment_name: str
    ) -> tuple[SourceFreshnessRecord, ...]:
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

    def replace_virtual_environment_seed_refs(
        self,
        connection: Any,
        *,
        schema: str,
        virtual_environment_name: str,
        refs: tuple[VirtualEnvironmentSeedRefRecord, ...],
    ) -> None:
        return None

    def get_virtual_environment_seed_refs(
        self, connection: Any, *, schema: str, virtual_environment_name: str
    ) -> tuple[VirtualEnvironmentSeedRefRecord, ...]:
        return ()

    def upsert_virtual_environment_python_node_ref(
        self,
        connection: Any,
        *,
        schema: str,
        ref: VirtualEnvironmentPythonNodeRefRecord,
    ) -> None:
        return None

    def get_virtual_environment_python_node_refs(
        self, connection: Any, *, schema: str, virtual_environment_name: str
    ) -> tuple[VirtualEnvironmentPythonNodeRefRecord, ...]:
        return ()

    def count_unreferenced_python_node_versions(self, connection: Any, *, schema: str) -> int:
        return 0

    def prune_unreferenced_python_node_versions(self, connection: Any, *, schema: str) -> int:
        return 0

    def create_virtual_environment_checkpoint(
        self,
        connection: Any,
        *,
        schema: str,
        checkpoint: VirtualEnvironmentCheckpointRecord,
        refs: tuple[VirtualEnvironmentCheckpointModelRefRecord, ...],
        function_refs: tuple[VirtualEnvironmentCheckpointFunctionRefRecord, ...] = (),
        seed_refs: tuple[VirtualEnvironmentCheckpointSeedRefRecord, ...] = (),
    ) -> None:
        return None

    def list_virtual_environment_checkpoints(
        self, connection: Any, *, schema: str, virtual_environment_name: str
    ) -> tuple[VirtualEnvironmentCheckpointRecord, ...]:
        return ()

    def get_virtual_environment_checkpoint_model_refs(
        self, connection: Any, *, schema: str, checkpoint_id: str
    ) -> tuple[VirtualEnvironmentCheckpointModelRefRecord, ...]:
        return ()

    def get_virtual_environment_checkpoint_function_refs(
        self, connection: Any, *, schema: str, checkpoint_id: str
    ) -> tuple[VirtualEnvironmentCheckpointFunctionRefRecord, ...]:
        return ()

    def get_virtual_environment_checkpoint_seed_refs(
        self, connection: Any, *, schema: str, checkpoint_id: str
    ) -> tuple[VirtualEnvironmentCheckpointSeedRefRecord, ...]:
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

    def list_expired_locks(self, connection: Any, *, schema: str) -> tuple[StateLockRecord, ...]:
        return ()

    def delete_lock(self, connection: Any, *, schema: str, lock_key: str) -> None:
        return None

    def list_state_backups(self, connection: Any, *, schema: str) -> tuple[StateBackupRecord, ...]:
        return ()

    def delete_state_backup(self, connection: Any, *, schema: str, backup_id: str) -> None:
        return None
