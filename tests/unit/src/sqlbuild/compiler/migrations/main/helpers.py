"""Event builders for model migration state unit tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlbuild.compiler.migrations.main.deterministic_event_id import (
    deterministic_migration_event_id,
)
from sqlbuild.compiler.migrations.models import MigrationEvent, MigrationRelation
from sqlbuild.compiler.migrations.types import MigrationDecision, MigrationDiscovery

_STARTED_AT: datetime = datetime(2026, 1, 1, tzinfo=UTC)


def main_relation(name: str) -> MigrationRelation:
    """Return a relation in the main schema with no database qualifier."""

    return MigrationRelation(database=None, schema="main", name=name)


def migration_event(*, origin: str, destination: str, day: int) -> MigrationEvent:
    """Return a manual migrate event recorded on the given day."""

    return MigrationEvent(
        event_id=deterministic_migration_event_id(
            run_id=f"run-{day}",
            target_name="dev",
            origin=main_relation(origin),
            destination=main_relation(destination),
        ),
        target_name="dev",
        origin_model=origin,
        origin=main_relation(origin),
        destination_model=destination,
        destination=main_relation(destination),
        origin_version_hash=f"hash-{origin}",
        discovery=MigrationDiscovery.MANUAL,
        decision=MigrationDecision.MIGRATE,
        run_id=f"run-{day}",
        created_at=_STARTED_AT + timedelta(days=day),
    )
