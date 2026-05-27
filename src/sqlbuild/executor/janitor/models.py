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
class JanitorPlan:
    """Complete janitor preview and execution plan."""

    environment_name: str | None
    retention_days: int
    candidates: tuple[JanitorDeleteCandidate, ...] = field(default_factory=tuple)
    checkpoint_candidates: tuple[JanitorCheckpointCandidate, ...] = field(default_factory=tuple)
    skipped_relations: tuple[JanitorSkippedRelation, ...] = field(default_factory=tuple)
    skipped_schemas: tuple[JanitorSkippedSchema, ...] = field(default_factory=tuple)
    scanned_schema_count: int = 0
    age_metadata_supported: bool = False


@dataclass(frozen=True)
class JanitorExecutionResult:
    """Result from deleting janitor candidates."""

    deleted: tuple[JanitorDeleteCandidate, ...] = field(default_factory=tuple)
    deleted_checkpoints: tuple[JanitorCheckpointCandidate, ...] = field(default_factory=tuple)
