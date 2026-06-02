"""Virtual state store models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sqlbuild.virtual.state.types import (
    ModelVersionStatus,
    ReconcileAction,
    StateBackendName,
    StateOperationStatus,
    StateOperationType,
    StateSchemaValidationIssueKind,
    VirtualEnvironmentStatus,
)


@dataclass(frozen=True)
class StateBackendConfig:
    """Resolved state backend configuration."""

    backend: StateBackendName
    schema: str
    connection: dict[str, object]
    allow_reset: bool = False


@dataclass(frozen=True)
class StateSchemaValidationIssue:
    """One state schema validation issue."""

    kind: StateSchemaValidationIssueKind
    table_name: str
    message: str
    column_name: str | None = None


@dataclass(frozen=True)
class StateSchemaValidationResult:
    """State schema validation result."""

    issues: tuple[StateSchemaValidationIssue, ...] = field(default_factory=tuple)

    @property
    def valid(self) -> bool:
        return not self.issues


@dataclass(frozen=True)
class ModelVersionRecord:
    """Current state row for one model version."""

    model_name: str
    version_hash: str
    data_hash: str
    metadata_hash: str
    status: ModelVersionStatus
    fingerprint_query_sql_b64: str | None = None
    fingerprint_metadata_json_b64: str | None = None
    compiled_sql_b64: str | None = None


@dataclass(frozen=True)
class PhysicalRelationRecord:
    """Current state row for a physical relation that stores one model version."""

    model_name: str
    version_hash: str
    database_name: str | None
    schema_name: str
    relation_name: str
    relation_type: str


@dataclass(frozen=True)
class PhysicalRelationAncestryRecord:
    """State row linking a seeded physical relation to its source relation."""

    model_name: str
    version_hash: str
    parent_model_name: str
    parent_version_hash: str
    seed_strategy: str


@dataclass(frozen=True)
class FunctionVersionRecord:
    """Current state row for one function version."""

    function_name: str
    version_hash: str
    language: str
    returns: str
    arguments_json_b64: str
    return_columns_json_b64: str
    packages_json_b64: str
    body_sql_b64: str
    fingerprint_query_sql_b64: str
    status: ModelVersionStatus
    runtime_version: str | None = None
    entry_point: str | None = None


@dataclass(frozen=True)
class VirtualEnvironmentRecord:
    """Current state row for one virtual data environment."""

    virtual_target_name: str
    status: VirtualEnvironmentStatus
    baseline_virtual_target_name: str | None = None
    finalized_at: datetime | None = None


@dataclass(frozen=True)
class VirtualEnvironmentRetentionRecord:
    """Virtual data environment retention metadata."""

    virtual_target_name: str
    status: VirtualEnvironmentStatus
    updated_at: datetime | None = None


@dataclass(frozen=True)
class VirtualEnvironmentRefRecord:
    """Current state row mapping a VDE model ref to a model version."""

    virtual_target_name: str
    model_name: str
    version_hash: str


@dataclass(frozen=True)
class VirtualEnvironmentFunctionRefRecord:
    """Current state row mapping a VDE function ref to a function version."""

    virtual_target_name: str
    function_name: str
    version_hash: str


@dataclass(frozen=True)
class VirtualEnvironmentCheckpointRecord:
    """Finalized checkpoint for one virtual data environment."""

    checkpoint_id: str
    virtual_target_name: str
    created_at: datetime | None = None


@dataclass(frozen=True)
class VirtualEnvironmentCheckpointRefRecord:
    """Checkpoint row mapping a model ref to a model version."""

    checkpoint_id: str
    model_name: str
    version_hash: str


@dataclass(frozen=True)
class VirtualEnvironmentCheckpointFunctionRefRecord:
    """Checkpoint row mapping a function ref to a function version."""

    checkpoint_id: str
    function_name: str
    version_hash: str


@dataclass(frozen=True)
class CheckpointRetentionInspection:
    """Checkpoint retention inspection for janitor planning."""

    prune_checkpoints: tuple[VirtualEnvironmentCheckpointRecord, ...]
    retained_physical_relations: tuple[PhysicalRelationRecord, ...]


@dataclass(frozen=True)
class DetachedVirtualEnvironmentInspection:
    """Detached VDE cleanup inspection for janitor planning."""

    cleanup_virtual_environments: tuple[VirtualEnvironmentRetentionRecord, ...]
    cleanup_physical_relations: tuple[PhysicalRelationRecord, ...]
    retained_physical_relations: tuple[PhysicalRelationRecord, ...]


@dataclass(frozen=True)
class ExpiredVirtualEnvironmentInspection:
    """Non-active VDE cleanup inspection for janitor planning."""

    cleanup_virtual_environments: tuple[VirtualEnvironmentRetentionRecord, ...]
    cleanup_physical_relations: tuple[PhysicalRelationRecord, ...]
    retained_physical_relations: tuple[PhysicalRelationRecord, ...]


@dataclass(frozen=True)
class StateJanitorInspection:
    """State-only janitor cleanup candidates."""

    state_backups: tuple[StateBackupRecord, ...]
    expired_locks: tuple[StateLockRecord, ...]


@dataclass(frozen=True)
class StateLockRecord:
    """Current state row for one active lock."""

    lock_key: str
    owner_id: str
    expires_at: datetime


@dataclass(frozen=True)
class StateBackupRecord:
    """One state migration backup schema."""

    backup_id: str
    schema_name: str
    created_at: datetime | None = None


@dataclass(frozen=True)
class StateLockLease:
    """Acquired state lock lease."""

    lock_key: str
    owner_id: str
    expires_at: datetime


@dataclass(frozen=True)
class StateOperationRecord:
    """Current state row for one tracked multi-step virtual operation."""

    operation_id: str
    operation_type: StateOperationType
    status: StateOperationStatus
    virtual_target_name: str | None = None


@dataclass(frozen=True)
class StateOperationEventRecord:
    """Append-only event row for one tracked operation."""

    event_id: str
    operation_id: str
    action: str
    status: StateOperationStatus
    message: str | None = None


@dataclass(frozen=True)
class ReconcileEventRecord:
    """Append-only event row for virtual reconcile actions."""

    event_id: str
    action: ReconcileAction
    status: StateOperationStatus
    message: str | None = None
