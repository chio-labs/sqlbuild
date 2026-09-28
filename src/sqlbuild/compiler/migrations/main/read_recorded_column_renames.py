"""Read the column renames recorded on one relation since a point in time."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from sqlbuild.adapter.contract.types import AdapterExecute
from sqlbuild.compiler.migrations.main._read_column_events import read_column_migration_events
from sqlbuild.compiler.migrations.models import ColumnMigrationEvent, MigrationRelation


def read_recorded_column_renames(
    *,
    connection: Any,
    execute: AdapterExecute[Any, Any],
    relation: MigrationRelation,
    since: datetime,
    render_qualified_name: Callable[..., str | None],
) -> tuple[ColumnMigrationEvent, ...]:
    """Return renames recorded on the relation at or after ``since``, oldest first."""

    return tuple(
        sorted(
            (
                event
                for event in read_column_migration_events(
                    connection=connection,
                    execute=execute,
                    database=relation.database,
                    schema=relation.schema or "",
                    render_qualified_name=render_qualified_name,
                )
                if event.relation.matches(relation)
                and event.decision.records_event
                and event.created_at >= since
            ),
            key=lambda event: (event.created_at, event.event_id),
        )
    )
