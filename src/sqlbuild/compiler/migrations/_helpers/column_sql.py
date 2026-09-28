"""Portable SQL for append-only column migration events."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlbuild.adapter.contract.types import FrameworkType
from sqlbuild.adapter.state_sql.main.render_state_table_create_sql import (
    render_state_table_create_sql,
)
from sqlbuild.compiler.migrations._helpers.sql import (
    decode_event_timestamp,
    optional_text,
    render_event_exists_sql,
    render_event_insert_sql,
)
from sqlbuild.compiler.migrations.constants import (
    COLUMN_MIGRATION_COLUMN_TYPES,
    COLUMN_MIGRATION_COLUMNS,
    COLUMN_MIGRATION_TABLE_NAME,
)
from sqlbuild.compiler.migrations.exceptions import MigrationStateError
from sqlbuild.compiler.migrations.models import ColumnMigrationEvent, MigrationRelation
from sqlbuild.compiler.migrations.types import ColumnMigrationDecision, MigrationDiscovery


def qualified_column_migration_table(
    *, database: str | None, schema: str, render_qualified_name: Callable[..., str | None]
) -> str:
    table: str | None = render_qualified_name(
        database=database, schema=schema, name=COLUMN_MIGRATION_TABLE_NAME
    )
    if table is None:
        raise MigrationStateError("column migration state requires a target schema")
    return table


def build_column_create_table_sql(
    *,
    database: str | None,
    schema: str,
    render_qualified_name: Callable[..., str | None],
    render_framework_type: Callable[[FrameworkType], str],
    transient: bool,
) -> str:
    return render_state_table_create_sql(
        qualified_name=qualified_column_migration_table(
            database=database, schema=schema, render_qualified_name=render_qualified_name
        ),
        columns=COLUMN_MIGRATION_COLUMNS,
        column_types=COLUMN_MIGRATION_COLUMN_TYPES,
        required_columns=frozenset(),
        render_framework_type=render_framework_type,
        transient=transient,
    )


def build_column_existing_event_sql(
    *, event: ColumnMigrationEvent, render_qualified_name: Callable[..., str | None]
) -> str:
    return render_event_exists_sql(
        table=_event_table(event=event, render_qualified_name=render_qualified_name),
        event_id=event.event_id,
    )


def build_column_insert_sql(
    *, event: ColumnMigrationEvent, render_qualified_name: Callable[..., str | None]
) -> str:
    return render_event_insert_sql(
        table=_event_table(event=event, render_qualified_name=render_qualified_name),
        columns=COLUMN_MIGRATION_COLUMNS,
        column_types=COLUMN_MIGRATION_COLUMN_TYPES,
        values=(
            event.event_id,
            event.target_name,
            event.model_name,
            event.relation.database,
            event.relation.schema,
            event.relation.name,
            event.origin_column,
            event.destination_column,
            event.discovery.value,
            event.decision.value,
            event.run_id,
            event.created_at,
        ),
    )


def build_column_read_sql(
    *, database: str | None, schema: str, render_qualified_name: Callable[..., str | None]
) -> str:
    table: str = qualified_column_migration_table(
        database=database, schema=schema, render_qualified_name=render_qualified_name
    )
    return (
        f"SELECT {', '.join(COLUMN_MIGRATION_COLUMNS)} FROM {table} ORDER BY created_at, event_id"
    )


def decode_column_event_row(row: tuple[Any, ...]) -> ColumnMigrationEvent:
    values: dict[str, Any] = dict(zip(COLUMN_MIGRATION_COLUMNS, row, strict=False))
    return ColumnMigrationEvent(
        event_id=str(values["event_id"]),
        target_name=optional_text(values["target_name"]),
        model_name=str(values["model_name"]),
        relation=MigrationRelation(
            database=optional_text(values["relation_database"]),
            schema=optional_text(values["relation_schema"]),
            name=str(values["relation_name"]),
        ),
        origin_column=str(values["origin_column"]),
        destination_column=str(values["destination_column"]),
        discovery=MigrationDiscovery(str(values["discovery"])),
        decision=ColumnMigrationDecision(str(values["decision"])),
        run_id=str(values["run_id"]),
        created_at=decode_event_timestamp(values["created_at"]),
    )


def _event_table(
    *, event: ColumnMigrationEvent, render_qualified_name: Callable[..., str | None]
) -> str:
    if event.relation.schema is None:
        raise MigrationStateError("column migration events require a relation schema")
    return qualified_column_migration_table(
        database=event.relation.database,
        schema=event.relation.schema,
        render_qualified_name=render_qualified_name,
    )
