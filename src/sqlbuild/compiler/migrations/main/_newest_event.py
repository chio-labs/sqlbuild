"""Project the newest migration event that mentions one relation."""

from __future__ import annotations

from collections.abc import Iterable

from sqlbuild.compiler.migrations.models import MigrationEvent, MigrationRelation


def newest_migration_event_mentioning(
    *, events: Iterable[MigrationEvent], relation: MigrationRelation
) -> MigrationEvent | None:
    """Return the latest event naming the relation as origin or destination."""

    newest: MigrationEvent | None = None
    event: MigrationEvent
    for event in events:
        if not event.mentions(relation):
            continue
        if newest is None or (event.created_at, event.event_id) > (
            newest.created_at,
            newest.event_id,
        ):
            newest = event
    return newest
