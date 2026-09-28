"""Stable model migration value types."""

from __future__ import annotations

from enum import StrEnum


class MigrationDecision(StrEnum):
    """Per-run decision for one declared or discovered model migration."""

    DONE = "done"
    MIGRATE = "migrate"
    REDO = "redo"
    SUPERSEDED_REPLACE = "superseded_replace"
    FORCED_REPLACE = "forced_replace"
    CONFLICT = "conflict"
    ORIGIN_MISSING = "origin_missing"
    RENAMED = "renamed"

    @property
    def moves_data(self) -> bool:
        """Return whether this decision clones the origin over the destination."""

        return self in _MOVING_DECISIONS

    @property
    def blocks_build(self) -> bool:
        """Return whether this decision stops a build regardless of compatibility."""

        return self in _BLOCKING_DECISIONS

    @property
    def checks_compatibility(self) -> bool:
        """Return whether this decision evaluated the origin against the destination."""

        return self.moves_data or self == MigrationDecision.CONFLICT

    @property
    def label(self) -> str:
        """Return the human-readable plan label for this decision."""

        return self.value.replace("_", " ")


_MOVING_DECISIONS: frozenset[MigrationDecision] = frozenset(
    {
        MigrationDecision.MIGRATE,
        MigrationDecision.REDO,
        MigrationDecision.SUPERSEDED_REPLACE,
        MigrationDecision.FORCED_REPLACE,
    }
)
_BLOCKING_DECISIONS: frozenset[MigrationDecision] = frozenset(
    {MigrationDecision.CONFLICT, MigrationDecision.ORIGIN_MISSING}
)


class MigrationDiscovery(StrEnum):
    """How a migration was requested."""

    MANUAL = "manual"
    AUTOMATIC = "automatic"


class MigrationPromotion(StrEnum):
    """How a completed migration stage replaces or creates the destination."""

    SWAP = "swap"
    RENAME = "rename"
    TRANSACTIONAL_RENAME = "transactional_rename"

    @property
    def label(self) -> str:
        """Return the human-readable plan label for this promotion."""

        return self.value.replace("_", " ")


class MigrationCompatibility(StrEnum):
    """Outcome of checking the origin relation against the destination model."""

    COMPATIBLE = "compatible"
    INCOMPATIBLE = "incompatible"
    NOT_CHECKED = "not_checked"


class ColumnMigrationDecision(StrEnum):
    """Per-run decision for one declared or detected column rename."""

    RENAME = "rename"
    RECORD = "record"
    DONE = "done"
    CONFLICT = "conflict"
    SOURCE_MISSING = "source_missing"
    STILL_PRODUCED = "still_produced"
    UNSUPPORTED = "unsupported"

    @property
    def renames(self) -> bool:
        """Return whether this decision renames the warehouse column."""

        return self == ColumnMigrationDecision.RENAME

    @property
    def records_event(self) -> bool:
        """Return whether this decision appends a column migration event."""

        return self in _RECORDING_COLUMN_DECISIONS

    @property
    def blocks_build(self) -> bool:
        """Return whether this decision stops a build before any execution."""

        return self in _BLOCKING_COLUMN_DECISIONS

    @property
    def label(self) -> str:
        """Return the human-readable plan label for this decision."""

        return _COLUMN_DECISION_LABELS[self]


class OldNameViewEventType(StrEnum):
    """Immutable facts about what happened at a migrated relation's old name."""

    REQUIRED = "required"
    ORIGIN_ARCHIVED = "origin_archived"
    VIEW_CREATED = "view_created"
    VIEW_DROPPED = "view_dropped"


class OldNameViewDropReason(StrEnum):
    """Why a compatibility view at an old name was dropped."""

    EXPIRED = "expired"
    EARLY = "early"
    MISSING = "missing"


class OldNameViewStatus(StrEnum):
    """Projected state of the old-name steps of one recorded move."""

    PENDING_ARCHIVE = "pending_archive"
    PENDING_VIEW = "pending_view"
    LIVE = "live"
    EXPIRED = "expired"
    DROPPED = "dropped"


class OldNameViewAction(StrEnum):
    """What a build does at a migrated model's old name."""

    ARCHIVE_AND_VIEW = "archive_and_view"
    VIEW_ONLY = "view_only"
    LIVE = "live"
    NONE = "none"


_RECORDING_COLUMN_DECISIONS: frozenset[ColumnMigrationDecision] = frozenset(
    {ColumnMigrationDecision.RENAME, ColumnMigrationDecision.RECORD}
)
_BLOCKING_COLUMN_DECISIONS: frozenset[ColumnMigrationDecision] = frozenset(
    {
        ColumnMigrationDecision.CONFLICT,
        ColumnMigrationDecision.SOURCE_MISSING,
        ColumnMigrationDecision.STILL_PRODUCED,
        ColumnMigrationDecision.UNSUPPORTED,
    }
)
_COLUMN_DECISION_LABELS: dict[ColumnMigrationDecision, str] = {
    ColumnMigrationDecision.RENAME: "rename in place",
    ColumnMigrationDecision.RECORD: "already renamed, record",
    ColumnMigrationDecision.DONE: "done",
    ColumnMigrationDecision.CONFLICT: "conflict",
    ColumnMigrationDecision.SOURCE_MISSING: "source missing",
    ColumnMigrationDecision.STILL_PRODUCED: "source still produced",
    ColumnMigrationDecision.UNSUPPORTED: "unsupported",
}
