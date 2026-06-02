"""State backend contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from sqlbuild.virtual.state.models import (
    FunctionVersionRecord,
    ModelVersionRecord,
    PhysicalRelationAncestryRecord,
    PhysicalRelationRecord,
    ReconcileEventRecord,
    StateBackupRecord,
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
    VirtualEnvironmentRetentionRecord,
)


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
    def initialize(self, connection: Any, *, schema: str, sqlbuild_version: str) -> None:
        """Create or migrate initial state schema objects."""
        ...

    @abstractmethod
    def validate_schema(self, connection: Any, *, schema: str) -> StateSchemaValidationResult:
        """Validate required state schema objects."""
        ...

    @abstractmethod
    def create_backup(self, connection: Any, *, schema: str) -> str:
        """Create a backup set and return its backup id."""
        ...

    @abstractmethod
    def rollback(self, connection: Any, *, schema: str, backup_id: str | None = None) -> str:
        """Restore state tables from a backup and return the used backup id."""
        ...

    @abstractmethod
    def reset(self, connection: Any, *, schema: str) -> None:
        """Drop state tables for the configured schema."""
        ...

    @abstractmethod
    def upsert_model_version(
        self, connection: Any, *, schema: str, record: ModelVersionRecord
    ) -> None:
        """Insert or replace a model version row."""
        ...

    @abstractmethod
    def get_model_version(
        self, connection: Any, *, schema: str, model_name: str, version_hash: str
    ) -> ModelVersionRecord | None:
        """Return a model version row if it exists."""
        ...

    @abstractmethod
    def upsert_function_version(
        self, connection: Any, *, schema: str, record: FunctionVersionRecord
    ) -> None:
        """Insert or replace a function version row."""
        ...

    @abstractmethod
    def get_function_version(
        self, connection: Any, *, schema: str, function_name: str, version_hash: str
    ) -> FunctionVersionRecord | None:
        """Return a function version row if it exists."""
        ...

    @abstractmethod
    def upsert_physical_relation(
        self, connection: Any, *, schema: str, record: PhysicalRelationRecord
    ) -> None:
        """Insert or replace a physical relation row."""
        ...

    @abstractmethod
    def get_physical_relation(
        self, connection: Any, *, schema: str, model_name: str, version_hash: str
    ) -> PhysicalRelationRecord | None:
        """Return a physical relation row if it exists."""
        ...

    @abstractmethod
    def list_physical_relations_for_model(
        self, connection: Any, *, schema: str, model_name: str
    ) -> tuple[PhysicalRelationRecord, ...]:
        """Return tracked physical relations for one model, newest first when available."""
        ...

    @abstractmethod
    def upsert_physical_relation_ancestry(
        self, connection: Any, *, schema: str, record: PhysicalRelationAncestryRecord
    ) -> None:
        """Insert or replace physical relation ancestry."""
        ...

    @abstractmethod
    def get_physical_relation_ancestry(
        self, connection: Any, *, schema: str, model_name: str, version_hash: str
    ) -> PhysicalRelationAncestryRecord | None:
        """Return physical relation ancestry if it exists."""
        ...

    @abstractmethod
    def upsert_virtual_environment(
        self, connection: Any, *, schema: str, record: VirtualEnvironmentRecord
    ) -> None:
        """Insert or replace a virtual environment row."""
        ...

    @abstractmethod
    def get_virtual_environment(
        self, connection: Any, *, schema: str, virtual_environment_name: str
    ) -> VirtualEnvironmentRecord | None:
        """Return a virtual environment row if it exists."""
        ...

    @abstractmethod
    def list_virtual_environments(
        self, connection: Any, *, schema: str
    ) -> tuple[VirtualEnvironmentRetentionRecord, ...]:
        """Return virtual environment retention metadata."""
        ...

    @abstractmethod
    def delete_virtual_environment(
        self, connection: Any, *, schema: str, virtual_environment_name: str
    ) -> None:
        """Delete a virtual environment and its current refs."""
        ...

    @abstractmethod
    def replace_virtual_environment_refs(
        self,
        connection: Any,
        *,
        schema: str,
        virtual_environment_name: str,
        refs: tuple[VirtualEnvironmentRefRecord, ...],
    ) -> None:
        """Replace all refs for a virtual environment."""
        ...

    @abstractmethod
    def get_virtual_environment_refs(
        self, connection: Any, *, schema: str, virtual_environment_name: str
    ) -> tuple[VirtualEnvironmentRefRecord, ...]:
        """Return refs for a virtual environment."""
        ...

    @abstractmethod
    def replace_virtual_environment_function_refs(
        self,
        connection: Any,
        *,
        schema: str,
        virtual_environment_name: str,
        refs: tuple[VirtualEnvironmentFunctionRefRecord, ...],
    ) -> None:
        """Replace all function refs for a virtual environment."""
        ...

    @abstractmethod
    def get_virtual_environment_function_refs(
        self, connection: Any, *, schema: str, virtual_environment_name: str
    ) -> tuple[VirtualEnvironmentFunctionRefRecord, ...]:
        """Return function refs for a virtual environment."""
        ...

    @abstractmethod
    def create_virtual_environment_checkpoint(
        self,
        connection: Any,
        *,
        schema: str,
        checkpoint: VirtualEnvironmentCheckpointRecord,
        refs: tuple[VirtualEnvironmentCheckpointRefRecord, ...],
        function_refs: tuple[VirtualEnvironmentCheckpointFunctionRefRecord, ...] = (),
    ) -> None:
        """Create a finalized virtual environment checkpoint."""
        ...

    @abstractmethod
    def list_virtual_environment_checkpoints(
        self, connection: Any, *, schema: str, virtual_environment_name: str
    ) -> tuple[VirtualEnvironmentCheckpointRecord, ...]:
        """Return checkpoints for a virtual environment, newest first."""
        ...

    @abstractmethod
    def get_virtual_environment_checkpoint_refs(
        self, connection: Any, *, schema: str, checkpoint_id: str
    ) -> tuple[VirtualEnvironmentCheckpointRefRecord, ...]:
        """Return refs for a virtual environment checkpoint."""
        ...

    @abstractmethod
    def get_virtual_environment_checkpoint_function_refs(
        self, connection: Any, *, schema: str, checkpoint_id: str
    ) -> tuple[VirtualEnvironmentCheckpointFunctionRefRecord, ...]:
        """Return function refs for a virtual environment checkpoint."""
        ...

    @abstractmethod
    def delete_virtual_environment_checkpoint(
        self, connection: Any, *, schema: str, checkpoint_id: str
    ) -> None:
        """Delete one virtual environment checkpoint and its refs."""
        ...

    @abstractmethod
    def upsert_state_operation(
        self, connection: Any, *, schema: str, record: StateOperationRecord
    ) -> None:
        """Insert or replace a tracked virtual operation row."""
        ...

    @abstractmethod
    def get_state_operation(
        self, connection: Any, *, schema: str, operation_id: str
    ) -> StateOperationRecord | None:
        """Return a tracked virtual operation row if it exists."""
        ...

    @abstractmethod
    def create_state_operation_event(
        self, connection: Any, *, schema: str, record: StateOperationEventRecord
    ) -> None:
        """Append one state operation event row."""
        ...

    @abstractmethod
    def create_reconcile_event(
        self, connection: Any, *, schema: str, record: ReconcileEventRecord
    ) -> None:
        """Append one reconcile event row."""
        ...

    @abstractmethod
    def acquire_lock(
        self,
        connection: Any,
        *,
        schema: str,
        lock_key: str,
        owner_id: str,
        expires_at: datetime,
    ) -> bool:
        """Acquire or replace an expired lock."""
        ...

    @abstractmethod
    def release_lock(self, connection: Any, *, schema: str, lock_key: str, owner_id: str) -> bool:
        """Release a lock owned by the given owner."""
        ...

    @abstractmethod
    def list_active_locks(self, connection: Any, *, schema: str) -> tuple[StateLockRecord, ...]:
        """Return non-expired locks."""
        ...

    @abstractmethod
    def list_expired_locks(self, connection: Any, *, schema: str) -> tuple[StateLockRecord, ...]:
        """Return expired locks."""
        ...

    @abstractmethod
    def delete_lock(self, connection: Any, *, schema: str, lock_key: str) -> None:
        """Delete one lock by key."""
        ...

    @abstractmethod
    def list_state_backups(self, connection: Any, *, schema: str) -> tuple[StateBackupRecord, ...]:
        """Return state migration backup schemas known to the state store."""
        ...

    @abstractmethod
    def delete_state_backup(self, connection: Any, *, schema: str, backup_id: str) -> None:
        """Delete one state migration backup schema."""
        ...
