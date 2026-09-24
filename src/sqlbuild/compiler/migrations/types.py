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


class MigrationCompatibility(StrEnum):
    """Outcome of checking the origin relation against the destination model."""

    COMPATIBLE = "compatible"
    INCOMPATIBLE = "incompatible"
    NOT_CHECKED = "not_checked"
