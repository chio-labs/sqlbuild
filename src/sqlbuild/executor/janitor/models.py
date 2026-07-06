"""Janitor planning models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sqlbuild.adapter.shared.models import RelationInfo


@dataclass(frozen=True)
class JanitorRelationKey:
    """Physical identity for a warehouse relation considered by janitor."""

    database: str | None
    schema: str | None
    name: str

    def display_name(self) -> str:
        """Render a qualified display name."""

        parts: list[str] = []
        if self.database is not None:
            parts.append(self.database)
        if self.schema is not None:
            parts.append(self.schema)
        parts.append(self.name)
        return ".".join(parts)


@dataclass(frozen=True)
class JanitorDeleteCandidate:
    """One stale relation eligible for deletion."""

    key: JanitorRelationKey
    relation: RelationInfo
    age_timestamp: datetime | None


@dataclass(frozen=True)
class JanitorCheckpointCandidate:
    """One retained-history checkpoint eligible for pruning."""

    checkpoint_id: str
    virtual_environment_name: str
    created_at: datetime | None


@dataclass(frozen=True)
class JanitorDetachedVirtualEnvironmentCandidate:
    """One detached virtual environment eligible for state cleanup."""

    virtual_environment_name: str
    updated_at: datetime | None


@dataclass(frozen=True)
class JanitorExpiredVirtualEnvironmentCandidate:
    """One non-active virtual environment eligible for TTL cleanup."""

    virtual_environment_name: str
    updated_at: datetime | None


@dataclass(frozen=True)
class JanitorStateBackupCandidate:
    """One state migration backup eligible for pruning."""

    backup_id: str
    schema_name: str
    created_at: datetime | None


@dataclass(frozen=True)
class JanitorExpiredLockCandidate:
    """One expired state lock eligible for pruning."""

    lock_key: str
    owner_id: str
    expires_at: datetime


@dataclass(frozen=True)
class JanitorDirectStatePruneCandidate:
    """One direct-mode state table eligible for history pruning."""

    database: str | None
    schema: str
    table_name: str
    retain_versions: int
    prune_sql: str

    def display_name(self) -> str:
        parts: list[str] = []
        if self.database is not None:
            parts.append(self.database)
        parts.append(self.schema)
        parts.append(self.table_name)
        return ".".join(parts)


@dataclass(frozen=True)
class JanitorVirtualStatePruneCandidate:
    """One virtual-mode state table eligible for orphaned state pruning."""

    schema: str
    table_name: str
    reason: str

    def display_name(self) -> str:
        return f"{self.schema}.{self.table_name}"


@dataclass(frozen=True)
class JanitorSkippedRelation:
    """One stale relation skipped by a safety rule."""

    key: JanitorRelationKey
    reason: str
    relation: RelationInfo | None = None


@dataclass(frozen=True)
class JanitorSkippedSchema:
    """One target schema skipped because it contains configured sources."""

    database: str | None
    schema: str | None
    source_names: tuple[str, ...]
    skipped_relations: tuple[RelationInfo, ...] = field(default_factory=tuple)

    def display_name(self) -> str:
        """Render a schema display name."""

        if self.database is not None and self.schema is not None:
            return f"{self.database}.{self.schema}"
        if self.schema is not None:
            return self.schema
        if self.database is not None:
            return self.database
        return "<default>"


@dataclass(frozen=True)
class JanitorWarehouseFacts:
    """Desired, discovered, and tracked relation facts for planning."""

    desired_keys: frozenset[JanitorRelationKey]
    source_schema_names: dict[tuple[str | None, str | None], set[str]]
    relations_by_schema: dict[tuple[str | None, str | None], tuple[RelationInfo, ...]]
    tracked_relation_keys: frozenset[JanitorRelationKey]


@dataclass(frozen=True)
class JanitorRelationClassification:
    """Delete candidates and skipped relations for one target schema."""

    candidates: tuple[JanitorDeleteCandidate, ...]
    skipped_relations: tuple[JanitorSkippedRelation, ...]


@dataclass(frozen=True)
class JanitorPlan:
    """Complete janitor preview and execution plan."""

    target_name: str | None
    retention_days: int
    candidates: tuple[JanitorDeleteCandidate, ...] = field(default_factory=tuple)
    checkpoint_candidates: tuple[JanitorCheckpointCandidate, ...] = field(default_factory=tuple)
    detached_virtual_environment_candidates: tuple[
        JanitorDetachedVirtualEnvironmentCandidate, ...
    ] = field(default_factory=tuple)
    expired_virtual_environment_candidates: tuple[
        JanitorExpiredVirtualEnvironmentCandidate, ...
    ] = field(default_factory=tuple)
    state_backup_candidates: tuple[JanitorStateBackupCandidate, ...] = field(default_factory=tuple)
    expired_lock_candidates: tuple[JanitorExpiredLockCandidate, ...] = field(default_factory=tuple)
    direct_state_prune_candidates: tuple[JanitorDirectStatePruneCandidate, ...] = field(
        default_factory=tuple
    )
    virtual_state_prune_candidates: tuple[JanitorVirtualStatePruneCandidate, ...] = field(
        default_factory=tuple
    )
    skipped_relations: tuple[JanitorSkippedRelation, ...] = field(default_factory=tuple)
    skipped_schemas: tuple[JanitorSkippedSchema, ...] = field(default_factory=tuple)
    scanned_schema_count: int = 0
    age_metadata_supported: bool = False


@dataclass(frozen=True)
class JanitorExecutionResult:
    """Result from deleting janitor candidates."""

    deleted: tuple[JanitorDeleteCandidate, ...] = field(default_factory=tuple)
    deleted_checkpoints: tuple[JanitorCheckpointCandidate, ...] = field(default_factory=tuple)
    deleted_detached_virtual_environments: tuple[
        JanitorDetachedVirtualEnvironmentCandidate, ...
    ] = field(default_factory=tuple)
    deleted_expired_virtual_environments: tuple[JanitorExpiredVirtualEnvironmentCandidate, ...] = (
        field(default_factory=tuple)
    )
    deleted_state_backups: tuple[JanitorStateBackupCandidate, ...] = field(default_factory=tuple)
    deleted_expired_locks: tuple[JanitorExpiredLockCandidate, ...] = field(default_factory=tuple)
    pruned_direct_state: tuple[JanitorDirectStatePruneCandidate, ...] = field(default_factory=tuple)
    pruned_virtual_state: tuple[JanitorVirtualStatePruneCandidate, ...] = field(
        default_factory=tuple
    )
