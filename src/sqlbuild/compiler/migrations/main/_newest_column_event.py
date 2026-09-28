"""Project the newest column migration event that mentions a column pair."""

from __future__ import annotations

from collections.abc import Iterable

from sqlbuild.compiler.migrations.models import ColumnMigrationEvent, MigrationRelation


def newest_column_migration_event_mentioning(
    *,
    events: Iterable[ColumnMigrationEvent],
    relation: MigrationRelation,
    origin_column: str,
    destination_column: str,
) -> ColumnMigrationEvent | None:
    """Return the latest event on the relation that renamed either column."""

    columns: frozenset[str] = frozenset({origin_column.lower(), destination_column.lower()})
    newest: ColumnMigrationEvent | None = None
    event: ColumnMigrationEvent
    for event in events:
        if not event.mentions(relation=relation, columns=columns):
            continue
        if newest is None or (event.created_at, event.event_id) > (
            newest.created_at,
            newest.event_id,
        ):
            newest = event
    return newest
