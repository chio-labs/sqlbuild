"""State backend contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from sqlbuild.executor.node_results.models import (
    NodeResultEnvelope,
    NodeResultQuery,
    NodeResultRecord,
)
from sqlbuild.microbatches.exceptions import MicrobatchStateError
from sqlbuild.microbatches.models import MicrobatchEvent, MicrobatchScope
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
from sqlbuild.virtual.state.types import PhysicalArtifactType


class StateBackend(ABC):
    """State backend contract for virtual mode lifecycle operations."""

    @abstractmethod
    def connect(self, config: dict[str, object]) -> Any:
        """Open a state store connection."""
        ...

    @abstractmethod
    def close(self, connection: Any) -> None:
        """Close a state store connection."""
        ...

    @abstractmethod
    def initialize(self, *, connection: Any, schema: str, sqlbuild_version: str) -> None:
        """Create or migrate initial state schema objects."""
        ...

    @abstractmethod
    def inspect_schema(self, *, connection: Any, schema: str) -> StateSchemaValidationResult:
        """Inspect required state schema objects."""
        ...

    @abstractmethod
    def create_backup(self, *, connection: Any, schema: str) -> str:
        """Create a backup set and return its backup id."""
        ...

    @abstractmethod
    def rollback(self, *, connection: Any, schema: str, backup_id: str | None = None) -> str:
        """Restore state tables from a backup and return the used backup id."""
        ...

    @abstractmethod
    def reset(self, *, connection: Any, schema: str) -> None:
        """Drop state tables for the configured schema."""
        ...

    @abstractmethod
    def upsert_model_version(
        self, *, connection: Any, schema: str, record: ModelVersionRecord
    ) -> None:
        """Insert or replace a model version row."""
        ...

    @abstractmethod
    def get_model_version(
        self, *, connection: Any, schema: str, model_name: str, version_hash: str
    ) -> ModelVersionRecord | None:
        """Return a model version row if it exists."""
        ...

    @abstractmethod
    def upsert_function_version(
        self, *, connection: Any, schema: str, record: FunctionVersionRecord
    ) -> None:
        """Insert or replace a function version row."""
        ...

    @abstractmethod
    def get_function_version(
        self, *, connection: Any, schema: str, function_name: str, version_hash: str
    ) -> FunctionVersionRecord | None:
        """Return a function version row if it exists."""
        ...

    @abstractmethod
    def upsert_seed_version(
        self, *, connection: Any, schema: str, record: SeedVersionRecord
    ) -> None:
        """Insert or replace a seed version row."""
        ...

    @abstractmethod
    def get_seed_version(
        self, *, connection: Any, schema: str, seed_name: str, version_hash: str
    ) -> SeedVersionRecord | None:
        """Return a seed version row if it exists."""
        ...

    @abstractmethod
    def upsert_python_node_version(
        self, *, connection: Any, schema: str, record: PythonNodeVersionRecord
    ) -> None:
        """Insert or replace a Python node identity version row."""
        ...

    @abstractmethod
    def get_python_node_version(
        self,
        *,
        connection: Any,
        schema: str,
        node_type: str,
        node_name: str,
        version_hash: str,
    ) -> PythonNodeVersionRecord | None:
        """Return a Python node identity version row if it exists."""
        ...

    @abstractmethod
    def insert_node_result(
        self,
        *,
        connection: Any,
        schema: str,
        virtual_environment_name: str,
        record: NodeResultRecord,
    ) -> None:
        """Append one runtime node result row for a virtual environment."""
        ...

    @abstractmethod
    def read_node_results(
        self,
        *,
        connection: Any,
        schema: str,
        virtual_environment_name: str,
        query: NodeResultQuery,
    ) -> tuple[NodeResultEnvelope, ...]:
        """Read runtime node result rows for one virtual environment identity."""
        ...

    def append_microbatch_event(
        self, *, connection: Any, schema: str, event: MicrobatchEvent
    ) -> None:
        """Append one logical microbatch event to virtual state."""
        raise MicrobatchStateError("virtual state backend does not support microbatch events")

    def read_microbatch_scope_history(
        self, *, connection: Any, schema: str, scope: MicrobatchScope
    ) -> tuple[MicrobatchEvent, ...]:
        """Read ordered microbatch history for one physical scope."""
        raise MicrobatchStateError("virtual state backend does not support microbatch events")

    def read_microbatch_retention_history(
        self, *, connection: Any, schema: str
    ) -> tuple[MicrobatchEvent, ...]:
        """Read virtual microbatch history needed to derive active janitor roots."""
        raise MicrobatchStateError("virtual state backend does not support microbatch events")

    def read_microbatch_model_history(
        self, *, connection: Any, schema: str, scope: MicrobatchScope
    ) -> tuple[MicrobatchEvent, ...]:
        """Read virtual microbatch history for one model and warehouse realm."""
        raise MicrobatchStateError("virtual state backend does not support microbatch events")

    @abstractmethod
    def upsert_physical_relation(
        self, *, connection: Any, schema: str, record: PhysicalRelationRecord
    ) -> None:
        """Insert or replace a physical relation row."""
        ...

    @abstractmethod
    def get_physical_relation_for_artifact(
        self,
        *,
        connection: Any,
        schema: str,
        artifact_type: PhysicalArtifactType,
        artifact_name: str,
        version_hash: str,
    ) -> PhysicalRelationRecord | None:
        """Return a physical relation row for an artifact if it exists."""
        ...

    @abstractmethod
    def list_physical_relations_for_artifact(
        self,
        *,
        connection: Any,
        schema: str,
        artifact_type: PhysicalArtifactType,
        artifact_name: str,
    ) -> tuple[PhysicalRelationRecord, ...]:
        """Return tracked physical relations for one artifact, newest first when available."""
        ...

    def get_physical_relation(
        self, *, connection: Any, schema: str, model_name: str, version_hash: str
    ) -> PhysicalRelationRecord | None:
        """Return a physical model relation row if it exists."""
        return self.get_physical_relation_for_artifact(
            connection=connection,
            schema=schema,
            artifact_type=PhysicalArtifactType.MODEL,
            artifact_name=model_name,
            version_hash=version_hash,
        )

    def list_physical_relations_for_model(
        self, *, connection: Any, schema: str, model_name: str
    ) -> tuple[PhysicalRelationRecord, ...]:
        """Return tracked physical relations for one model, newest first when available."""
        return self.list_physical_relations_for_artifact(
            connection=connection,
            schema=schema,
            artifact_type=PhysicalArtifactType.MODEL,
            artifact_name=model_name,
        )

    @abstractmethod
    def upsert_physical_relation_ancestry(
        self, *, connection: Any, schema: str, record: PhysicalRelationAncestryRecord
    ) -> None:
        """Insert or replace physical relation ancestry."""
        ...

    @abstractmethod
    def get_physical_relation_ancestry(
        self, *, connection: Any, schema: str, model_name: str, version_hash: str
    ) -> PhysicalRelationAncestryRecord | None:
        """Return physical relation ancestry if it exists."""
        ...

    @abstractmethod
    def upsert_virtual_environment(
        self, *, connection: Any, schema: str, record: VirtualEnvironmentRecord
    ) -> None:
        """Insert or replace a virtual environment row."""
        ...

    @abstractmethod
    def get_virtual_environment(
        self, *, connection: Any, schema: str, virtual_environment_name: str
    ) -> VirtualEnvironmentRecord | None:
        """Return a virtual environment row if it exists."""
        ...

    @abstractmethod
    def list_virtual_environments(
        self, *, connection: Any, schema: str
    ) -> tuple[VirtualEnvironmentRetentionRecord, ...]:
        """Return virtual environment retention metadata."""
        ...

    @abstractmethod
    def delete_virtual_environment(
        self, *, connection: Any, schema: str, virtual_environment_name: str
    ) -> None:
        """Delete a virtual environment and its current refs."""
        ...

    @abstractmethod
    def replace_virtual_environment_node_refs(
        self,
        *,
        connection: Any,
        schema: str,
        virtual_environment_name: str,
        node_type: str,
        refs: tuple[VirtualEnvironmentNodeRefRecord, ...],
    ) -> None:
        """Replace all refs for one virtual environment node type."""
        ...

    @abstractmethod
    def replace_virtual_environment_node_ref_groups(
        self,
        *,
        connection: Any,
        schema: str,
        virtual_environment_name: str,
        refs_by_node_type: dict[str, tuple[VirtualEnvironmentNodeRefRecord, ...]],
    ) -> None:
        """Replace refs for multiple virtual environment node types atomically."""
        ...

    @abstractmethod
    def upsert_virtual_environment_and_replace_node_ref_groups(
        self,
        *,
        connection: Any,
        schema: str,
        record: VirtualEnvironmentRecord,
        refs_by_node_type: dict[str, tuple[VirtualEnvironmentNodeRefRecord, ...]],
    ) -> None:
        """Upsert a virtual environment and replace multiple ref groups atomically."""
        ...

    @abstractmethod
    def get_virtual_environment_node_refs(
        self,
        *,
        connection: Any,
        schema: str,
        virtual_environment_name: str,
        node_type: str,
    ) -> tuple[VirtualEnvironmentNodeRefRecord, ...]:
        """Return refs for one virtual environment node type."""
        ...

    @abstractmethod
    def upsert_virtual_environment_node_ref(
        self,
        *,
        connection: Any,
        schema: str,
        ref: VirtualEnvironmentNodeRefRecord,
    ) -> None:
        """Insert or replace one generic node ref for a virtual environment."""
        ...

    @abstractmethod
    def replace_virtual_environment_model_refs(
        self,
        *,
        connection: Any,
        schema: str,
        virtual_environment_name: str,
        refs: tuple[VirtualEnvironmentModelRefRecord, ...],
    ) -> None:
        """Replace all refs for a virtual environment."""
        ...

    @abstractmethod
    def get_virtual_environment_model_refs(
        self, *, connection: Any, schema: str, virtual_environment_name: str
    ) -> tuple[VirtualEnvironmentModelRefRecord, ...]:
        """Return refs for a virtual environment."""
        ...

    @abstractmethod
    def replace_virtual_environment_function_refs(
        self,
        *,
        connection: Any,
        schema: str,
        virtual_environment_name: str,
        refs: tuple[VirtualEnvironmentFunctionRefRecord, ...],
    ) -> None:
        """Replace all function refs for a virtual environment."""
        ...

    @abstractmethod
    def get_virtual_environment_function_refs(
        self, *, connection: Any, schema: str, virtual_environment_name: str
    ) -> tuple[VirtualEnvironmentFunctionRefRecord, ...]:
        """Return function refs for a virtual environment."""
        ...

    @abstractmethod
    def replace_virtual_environment_seed_refs(
        self,
        *,
        connection: Any,
        schema: str,
        virtual_environment_name: str,
        refs: tuple[VirtualEnvironmentSeedRefRecord, ...],
    ) -> None:
        """Replace all seed refs for a virtual environment."""
        ...

    @abstractmethod
    def get_virtual_environment_seed_refs(
        self, *, connection: Any, schema: str, virtual_environment_name: str
    ) -> tuple[VirtualEnvironmentSeedRefRecord, ...]:
        """Return seed refs for a virtual environment."""
        ...

    @abstractmethod
    def upsert_virtual_environment_python_node_ref(
        self,
        *,
        connection: Any,
        schema: str,
        ref: VirtualEnvironmentPythonNodeRefRecord,
    ) -> None:
        """Insert or replace one Python node ref for a virtual environment."""
        ...

    @abstractmethod
    def get_virtual_environment_python_node_refs(
        self, *, connection: Any, schema: str, virtual_environment_name: str
    ) -> tuple[VirtualEnvironmentPythonNodeRefRecord, ...]:
        """Return Python node refs for a virtual environment."""
        ...

    @abstractmethod
    def count_unreferenced_python_node_versions(self, *, connection: Any, schema: str) -> int:
        """Return count of Python node versions not referenced by any virtual environment."""
        ...

    @abstractmethod
    def prune_unreferenced_python_node_versions(self, *, connection: Any, schema: str) -> int:
        """Delete Python node versions not referenced by any virtual environment."""
        ...

    @abstractmethod
    def replace_virtual_environment_source_freshness(
        self,
        *,
        connection: Any,
        schema: str,
        virtual_environment_name: str,
        records: tuple[SourceFreshnessRecord, ...],
    ) -> None:
        """Replace all source freshness records for a virtual environment."""
        ...

    @abstractmethod
    def get_virtual_environment_source_freshness(
        self, *, connection: Any, schema: str, virtual_environment_name: str
    ) -> tuple[SourceFreshnessRecord, ...]:
        """Return source freshness records for a virtual environment."""
        ...

    @abstractmethod
    def create_virtual_environment_checkpoint(
        self,
        *,
        connection: Any,
        schema: str,
        checkpoint: VirtualEnvironmentCheckpointRecord,
        refs: tuple[VirtualEnvironmentCheckpointModelRefRecord, ...],
        function_refs: tuple[VirtualEnvironmentCheckpointFunctionRefRecord, ...] = (),
        seed_refs: tuple[VirtualEnvironmentCheckpointSeedRefRecord, ...] = (),
    ) -> None:
        """Create a finalized virtual environment checkpoint."""
        ...

    @abstractmethod
    def list_virtual_environment_checkpoints(
        self, *, connection: Any, schema: str, virtual_environment_name: str
    ) -> tuple[VirtualEnvironmentCheckpointRecord, ...]:
        """Return checkpoints for a virtual environment, newest first."""
        ...

    @abstractmethod
    def get_virtual_environment_checkpoint_model_refs(
        self, *, connection: Any, schema: str, checkpoint_id: str
    ) -> tuple[VirtualEnvironmentCheckpointModelRefRecord, ...]:
        """Return refs for a virtual environment checkpoint."""
        ...

    @abstractmethod
    def get_virtual_environment_checkpoint_function_refs(
        self, *, connection: Any, schema: str, checkpoint_id: str
    ) -> tuple[VirtualEnvironmentCheckpointFunctionRefRecord, ...]:
        """Return function refs for a virtual environment checkpoint."""
        ...

    @abstractmethod
    def get_virtual_environment_checkpoint_seed_refs(
        self, *, connection: Any, schema: str, checkpoint_id: str
    ) -> tuple[VirtualEnvironmentCheckpointSeedRefRecord, ...]:
        """Return seed refs for a virtual environment checkpoint."""
        ...

    @abstractmethod
    def delete_virtual_environment_checkpoint(
        self, *, connection: Any, schema: str, checkpoint_id: str
    ) -> None:
        """Delete one virtual environment checkpoint and its refs."""
        ...

    @abstractmethod
    def upsert_state_operation(
        self, *, connection: Any, schema: str, record: StateOperationRecord
    ) -> None:
        """Insert or replace a tracked virtual operation row."""
        ...

    @abstractmethod
    def get_state_operation(
        self, *, connection: Any, schema: str, operation_id: str
    ) -> StateOperationRecord | None:
        """Return a tracked virtual operation row if it exists."""
        ...

    @abstractmethod
    def create_state_operation_event(
        self, *, connection: Any, schema: str, record: StateOperationEventRecord
    ) -> None:
        """Append one state operation event row."""
        ...

    @abstractmethod
    def create_reconcile_event(
        self, *, connection: Any, schema: str, record: ReconcileEventRecord
    ) -> None:
        """Append one reconcile event row."""
        ...

    @abstractmethod
    def acquire_lock(
        self,
        *,
        connection: Any,
        schema: str,
        lock_key: str,
        owner_id: str,
        expires_at: datetime,
    ) -> bool:
        """Acquire or replace an expired lock."""
        ...

    def renew_lock(
        self,
        *,
        connection: Any,
        schema: str,
        lock_key: str,
        owner_id: str,
        expires_at: datetime,
    ) -> bool:
        """Renew a non-expired lock when ownership still matches."""

        return False

    @abstractmethod
    def release_lock(self, *, connection: Any, schema: str, lock_key: str, owner_id: str) -> bool:
        """Release a lock owned by the given owner."""
        ...

    @abstractmethod
    def list_active_locks(self, *, connection: Any, schema: str) -> tuple[StateLockRecord, ...]:
        """Return non-expired locks."""
        ...

    @abstractmethod
    def list_expired_locks(self, *, connection: Any, schema: str) -> tuple[StateLockRecord, ...]:
        """Return expired locks."""
        ...

    @abstractmethod
    def delete_lock(self, *, connection: Any, schema: str, lock_key: str) -> None:
        """Delete one lock by key."""
        ...

    @abstractmethod
    def list_state_backups(self, *, connection: Any, schema: str) -> tuple[StateBackupRecord, ...]:
        """Return state migration backup schemas known to the state store."""
        ...

    @abstractmethod
    def delete_state_backup(self, *, connection: Any, schema: str, backup_id: str) -> None:
        """Delete one state migration backup schema."""
        ...
