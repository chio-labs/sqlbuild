"""Build, read, and append old-name view facts during a build."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.migrations.constants import MIGRATION_WRITE_ATTEMPTS
from sqlbuild.compiler.migrations.main.deterministic_old_name_view_event_id import (
    deterministic_old_name_view_event_id,
)
from sqlbuild.compiler.migrations.main.read_old_name_view_events import (
    read_old_name_view_events,
)
from sqlbuild.compiler.migrations.main.relation_for_location import migration_relation_for_location
from sqlbuild.compiler.migrations.main.stored_old_name_view_columns import (
    stored_old_name_view_columns,
)
from sqlbuild.compiler.migrations.main.write_old_name_view_event import write_old_name_view_event
from sqlbuild.compiler.migrations.models import MigrationRelation, OldNameViewEvent
from sqlbuild.compiler.migrations.types import OldNameViewEventType
from sqlbuild.compiler.planner.models import OldNameViewPlanEntry


def old_name_fact(
    *,
    entry: OldNameViewPlanEntry,
    event_type: OldNameViewEventType,
    migration_event_id: str,
    run_id: str,
    created_at: datetime,
    archive_name: str | None = None,
    column_aliases: tuple[tuple[str, str], ...] = (),
    expires_at: datetime | None = None,
    grants_copied: tuple[str, ...] | None = None,
    view_sql: str | None = None,
) -> OldNameViewEvent:
    """Build one old-name fact for a planned old-name step."""

    return OldNameViewEvent(
        event_id=deterministic_old_name_view_event_id(
            event_type=event_type, migration_event_id=migration_event_id
        ),
        target_name=entry.target_name,
        event_type=event_type,
        migration_event_id=migration_event_id,
        destination_model=entry.model_name,
        old=migration_relation_for_location(entry.origin),
        new=migration_relation_for_location(entry.destination),
        run_id=run_id,
        created_at=created_at,
        view_retention=entry.retention if event_type == OldNameViewEventType.REQUIRED else None,
        archive_name=archive_name,
        column_aliases=column_aliases,
        expires_at=expires_at,
        grants_copied=grants_copied,
        view_sql=view_sql,
    )


def record_old_name_fact(
    *,
    adapter: BaseAdapter,
    connection: Any,
    event: OldNameViewEvent,
    create_table: bool = True,
    attempts: int = MIGRATION_WRITE_ATTEMPTS,
) -> None:
    """Append one old-name fact through the adapter's state-table rendering."""

    write_old_name_view_event(
        connection=connection,
        execute=adapter.execute,
        event=event,
        render_qualified_name=adapter.render_qualified_name,
        create_table_sql=(
            old_name_state_table_sql(adapter=adapter, relation=event.new) if create_table else None
        ),
        attempts=attempts,
    )


def old_name_state_table_sql(*, adapter: BaseAdapter, relation: MigrationRelation) -> str:
    """Render the create-if-missing DDL of the fact table next to one destination."""

    return adapter.render_create_old_name_view_state_table_sql(
        database=relation.database, schema=relation.schema or ""
    )


def recorded_old_name_facts(
    *, adapter: BaseAdapter, connection: Any, entry: OldNameViewPlanEntry, migration_event_id: str
) -> dict[OldNameViewEventType, OldNameViewEvent]:
    """Re-read the facts of one move so every step decides from current state."""

    relation: MigrationRelation = migration_relation_for_location(entry.destination)
    _ = adapter.execute(
        connection=connection, sql=old_name_state_table_sql(adapter=adapter, relation=relation)
    )
    facts: dict[OldNameViewEventType, OldNameViewEvent] = {}
    event: OldNameViewEvent
    for event in read_old_name_view_events(
        connection=connection,
        execute=adapter.execute,
        database=relation.database,
        schema=relation.schema or "",
        stored_columns=stored_old_name_view_columns(
            adapter=adapter,
            connection=connection,
            database=relation.database,
            schema=relation.schema or "",
        ),
        render_qualified_name=adapter.render_qualified_name,
    ):
        if event.migration_event_id == migration_event_id:
            _ = facts.setdefault(event.event_type, event)
    return facts
