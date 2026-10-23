"""Janitor planning models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sqlbuild._native import OldNameViewDropReason, OldNameViewHistory
from sqlbuild.adapter.contract.models import RelationInfo, RelationLookup
from sqlbuild.executor.janitor.types import JanitorAction
from sqlbuild.executor.janitor_events.models import JanitorEventRecord


@dataclass(frozen=True, eq=False)
class JanitorRelationKey:
    """Physical relation identity compared case-insensitively but rendered as spelled."""

    database: str | None
    schema: str | None
    name: str

    def identity(self) -> tuple[str | None, str | None, str]:
        """Return the case-insensitive comparison identity."""

        return RelationLookup.key(database=self.database, schema=self.schema, name=self.name)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, JanitorRelationKey):
            return NotImplemented
        return self.identity() == other.identity()

    def __hash__(self) -> int:
        return hash(self.identity())

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
class JanitorArchiveCandidate:
    """One stale direct-mode relation that will be renamed to an archive name."""

    key: JanitorRelationKey
    relation: RelationInfo
    age_timestamp: datetime | None
    archive_key: JanitorRelationKey
    archived_at: datetime
    expires_at: datetime


@dataclass(frozen=True)
class JanitorArchivedRelation:
    """One relation whose name strictly matches the janitor archive grammar."""

    key: JanitorRelationKey
    relation_type: str | None
    archived_at: datetime
    expires_at: datetime
    original_key: JanitorRelationKey | None = None


@dataclass(frozen=True)
class JanitorOldNameView:
    """One compatibility view recorded at a migrated model's old name."""

    key: JanitorRelationKey
    history: OldNameViewHistory
    expires_at: datetime | None
    drop_reason: OldNameViewDropReason | None = None
    occupied: bool = False
    claimed_by: str | None = None

    @property
    def destination_model(self) -> str:
        """Return the model whose relation the view reads."""

        return self.history.move.destination_model


@dataclass(frozen=True)
class JanitorOldNameViewPlanning:
    """Compatibility views to keep, drop, or record as already gone."""

    live: tuple[JanitorOldNameView, ...] = ()
    drops: tuple[JanitorOldNameView, ...] = ()
    missing: tuple[JanitorOldNameView, ...] = ()
    unknown_requests: tuple[str, ...] = ()
    project_destinations: dict[JanitorRelationKey, str] = field(default_factory=dict)

    @property
    def keys(self) -> frozenset[JanitorRelationKey]:
        """Return every old name this planning owns, so general cleanup leaves it alone."""

        return frozenset(view.key for view in (*self.live, *self.drops, *self.missing))


@dataclass(frozen=True)
class JanitorQueryDiffArtifactCandidate:
    """One expired, fingerprint-owned query-diff artifact eligible for deletion."""

    key: JanitorRelationKey


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
class JanitorBlockedSchema:
    """One direct-mode target schema blocked because it contains configured sources."""

    database: str | None
    schema: str | None
    source_names: tuple[str, ...]
    suppressed_candidates: tuple[JanitorDeleteCandidate, ...] = field(default_factory=tuple)
    suppressed_archive_deletions: tuple[JanitorArchivedRelation, ...] = field(default_factory=tuple)

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

    target_name: str | None
    retention_days: int
    direct_mode: bool = True
    archive_retention_days: int = 14
    candidates: tuple[JanitorDeleteCandidate, ...] = field(default_factory=tuple)
    archive_candidates: tuple[JanitorArchiveCandidate, ...] = field(default_factory=tuple)
    archive_deletion_candidates: tuple[JanitorArchivedRelation, ...] = field(default_factory=tuple)
    retained_archives: tuple[JanitorArchivedRelation, ...] = field(default_factory=tuple)
    query_diff_artifact_candidates: tuple[JanitorQueryDiffArtifactCandidate, ...] = field(
        default_factory=tuple
    )
    direct_state_prune_candidates: tuple[JanitorDirectStatePruneCandidate, ...] = field(
        default_factory=tuple
    )
    skipped_relations: tuple[JanitorSkippedRelation, ...] = field(default_factory=tuple)
    skipped_schemas: tuple[JanitorSkippedSchema, ...] = field(default_factory=tuple)
    blocked_schemas: tuple[JanitorBlockedSchema, ...] = field(default_factory=tuple)
    old_name_views: JanitorOldNameViewPlanning = field(default_factory=JanitorOldNameViewPlanning)
    scanned_schema_count: int = 0
    age_metadata_supported: bool = False
    planned_at: datetime | None = None


@dataclass(frozen=True)
class JanitorExecutionResult:
    """Result from deleting janitor candidates."""

    deleted: tuple[JanitorDeleteCandidate, ...] = field(default_factory=tuple)
    archived: tuple[JanitorArchiveCandidate, ...] = field(default_factory=tuple)
    deleted_archives: tuple[JanitorArchivedRelation, ...] = field(default_factory=tuple)
    deleted_query_diff_artifacts: tuple[JanitorQueryDiffArtifactCandidate, ...] = field(
        default_factory=tuple
    )
    pruned_direct_state: tuple[JanitorDirectStatePruneCandidate, ...] = field(default_factory=tuple)
    dropped_old_name_views: tuple[JanitorOldNameView, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class JanitorProgressItem:
    """How the progress output names one janitor action, and once finished its error and time."""

    action: JanitorAction
    name: str
    destination: str | None = None
    error: str | None = None
    duration_seconds: float = 0.0


@dataclass(frozen=True)
class JanitorActionOutcome[ResultT]:
    """What one janitor action returned or raised, and how long it ran."""

    result: ResultT | None = None
    error: BaseException | None = None
    duration_seconds: float = 0.0


@dataclass(frozen=True)
class JanitorChunkOutcome[ResultT]:
    """Each item's outcome in one chunk (none if never started), interrupt and report error."""

    outcomes: tuple[JanitorActionOutcome[ResultT] | None, ...]
    interruption: BaseException | None = None
    report_error: BaseException | None = None


@dataclass(frozen=True)
class JanitorActionDone:
    """A finished action: the action taken when it differs from the described one, and its event."""

    taken: JanitorAction | None = None
    event: JanitorEventRecord | None = None
