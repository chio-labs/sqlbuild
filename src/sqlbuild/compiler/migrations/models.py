"""Model migration state domain models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlbuild.compiler.migrations.types import MigrationDecision, MigrationDiscovery


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
