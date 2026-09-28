"""Model migration state domain models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlbuild.compiler.migrations.types import (
    ColumnMigrationDecision,
    MigrationDecision,
    MigrationDiscovery,
    OldNameViewDropReason,
    OldNameViewEventType,
    OldNameViewStatus,
)


@dataclass(frozen=True)
class MigrationRelation:
    """One physical relation named by a migration event."""

    database: str | None
    schema: str | None
    name: str

    @property
    def identity(self) -> tuple[str | None, str, str]:
        """Return the case-insensitive relation identity."""

        return (
            None if self.database is None else self.database.lower(),
            "" if self.schema is None else self.schema.lower(),
            self.name.lower(),
        )

    def matches(self, other: MigrationRelation) -> bool:
        """Compare relations, treating an unknown database as a wildcard."""

        left: tuple[str | None, str, str] = self.identity
        right: tuple[str | None, str, str] = other.identity
        if left[1:] != right[1:]:
            return False
        return left[0] is None or right[0] is None or left[0] == right[0]


@dataclass(frozen=True)
class MigrationEvent:
    """One immutable fact that a origin relation was cloned over a destination."""

    event_id: str
    target_name: str | None
    origin_model: str | None
    origin: MigrationRelation
    destination_model: str
    destination: MigrationRelation
    origin_version_hash: str
    discovery: MigrationDiscovery
    decision: MigrationDecision
    run_id: str
    created_at: datetime

    def mentions(self, relation: MigrationRelation) -> bool:
        """Return whether this event names the relation as origin or destination."""

        return self.origin.matches(relation) or self.destination.matches(relation)


@dataclass(frozen=True)
class ColumnMigrationEvent:
    """One immutable fact that a column of a model relation was renamed in place."""

    event_id: str
    target_name: str | None
    model_name: str
    relation: MigrationRelation
    origin_column: str
    destination_column: str
    discovery: MigrationDiscovery
    decision: ColumnMigrationDecision
    run_id: str
    created_at: datetime

    def mentions(self, *, relation: MigrationRelation, columns: frozenset[str]) -> bool:
        """Return whether this event renamed one of the columns of the relation."""

        return self.relation.matches(relation) and bool(
            {self.origin_column.lower(), self.destination_column.lower()} & columns
        )

    def renamed(self, *, origin_column: str, destination_column: str) -> bool:
        """Return whether this event renamed exactly this origin column to this destination."""

        return (
            self.origin_column.lower() == origin_column.lower()
            and self.destination_column.lower() == destination_column.lower()
        )


@dataclass(frozen=True)
class OldNameViewEvent:
    """One immutable fact about the old name of one recorded move."""

    event_id: str
    target_name: str | None
    event_type: OldNameViewEventType
    migration_event_id: str
    destination_model: str
    old: MigrationRelation
    new: MigrationRelation
    run_id: str
    created_at: datetime
    view_retention: str | None = None
    archive_name: str | None = None
    column_aliases: tuple[tuple[str, str], ...] = ()
    expires_at: datetime | None = None
    drop_reason: OldNameViewDropReason | None = None
    grants_copied: tuple[str, ...] | None = None
    view_sql: str | None = None


@dataclass(frozen=True)
class OldNameViewHistory:
    """The recorded move and every old-name fact that references it."""

    move: MigrationEvent
    required: OldNameViewEvent
    archived: OldNameViewEvent | None = None
    created: OldNameViewEvent | None = None
    dropped: OldNameViewEvent | None = None

    def status(self, *, now: datetime) -> OldNameViewStatus:
        """Project the current state of this move's old-name steps."""

        if self.dropped is not None:
            return OldNameViewStatus.DROPPED
        if self.created is not None:
            expires_at: datetime | None = self.created.expires_at
            if expires_at is not None and expires_at <= now:
                return OldNameViewStatus.EXPIRED
            return OldNameViewStatus.LIVE
        if self.archived is not None:
            return OldNameViewStatus.PENDING_VIEW
        return OldNameViewStatus.PENDING_ARCHIVE

    @property
    def old(self) -> MigrationRelation:
        """Return the relation name the compatibility view occupies."""

        return self.required.old

    @property
    def new(self) -> MigrationRelation:
        """Return the relation the compatibility view reads."""

        return self.required.new
