"""Portable SQL for append-only model migration events."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any

from sqlbuild.adapter.contract.types import FrameworkType
from sqlbuild.adapter.state_sql.main.render_state_table_create_sql import (
    render_state_table_create_sql,
)
from sqlbuild.compiler.migrations.constants import (
    MIGRATION_COLUMN_TYPES,
    MIGRATION_COLUMNS,
    MIGRATION_TABLE_NAME,
)
from sqlbuild.compiler.migrations.exceptions import MigrationStateError
from sqlbuild.compiler.migrations.models import MigrationEvent, MigrationRelation
from sqlbuild.compiler.migrations.types import MigrationDecision, MigrationDiscovery
from sqlbuild.sql_values.main.render_state_literal import render_state_sql_literal
from sqlbuild.sql_values.types import StateSqlValueType


def qualified_migration_table(
    *, database: str | None, schema: str, render_qualified_name: Callable[..., str | None]
) -> str:
    table: str | None = render_qualified_name(
        database=database, schema=schema, name=MIGRATION_TABLE_NAME
    )
    if table is None:
        raise MigrationStateError("model migration state requires a target schema")
    return table


def build_create_table_sql(
    *,
    database: str | None,
    schema: str,
    render_qualified_name: Callable[..., str | None],
    render_framework_type: Callable[[FrameworkType], str],
    transient: bool,
) -> str:
    return render_state_table_create_sql(
        qualified_name=qualified_migration_table(
            database=database, schema=schema, render_qualified_name=render_qualified_name
        ),
        columns=MIGRATION_COLUMNS,
        column_types=MIGRATION_COLUMN_TYPES,
        required_columns=frozenset(),
        render_framework_type=render_framework_type,
        transient=transient,
    )


def build_existing_event_sql(
    *, event: MigrationEvent, render_qualified_name: Callable[..., str | None]
) -> str:
    table: str = _event_table(event=event, render_qualified_name=render_qualified_name)
    return render_event_exists_sql(table=table, event_id=event.event_id)


def build_insert_sql(
    *, event: MigrationEvent, render_qualified_name: Callable[..., str | None]
) -> str:
    table: str = _event_table(event=event, render_qualified_name=render_qualified_name)
    return render_event_insert_sql(
        table=table,
        columns=MIGRATION_COLUMNS,
        column_types=MIGRATION_COLUMN_TYPES,
        values=_event_values(event),
    )


def render_event_exists_sql(*, table: str, event_id: str) -> str:
    """Render the lookup that makes an append-only event write idempotent."""

    event_id_literal: str = render_state_sql_literal(
        value=event_id, declared_type=StateSqlValueType.STRING
    )
    return f"SELECT event_id FROM {table} WHERE event_id = {event_id_literal}"


def render_event_insert_sql(
    *,
    table: str,
    columns: tuple[str, ...],
    column_types: Mapping[str, StateSqlValueType],
    values: tuple[object | None, ...],
) -> str:
    """Render one append-only event row as INSERT ... VALUES with typed literals."""

    literals: str = ", ".join(
        render_state_sql_literal(value=value, declared_type=column_types[column])
        for column, value in zip(columns, values, strict=True)
    )
    return f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({literals})"


def _event_table(*, event: MigrationEvent, render_qualified_name: Callable[..., str | None]) -> str:
    if event.destination.schema is None:
        raise MigrationStateError("model migration events require a destination schema")
    return qualified_migration_table(
        database=event.destination.database,
        schema=event.destination.schema,
        render_qualified_name=render_qualified_name,
    )


def build_read_sql(
    *, database: str | None, schema: str, render_qualified_name: Callable[..., str | None]
) -> str:
    table: str = qualified_migration_table(
        database=database, schema=schema, render_qualified_name=render_qualified_name
    )
    return f"SELECT {', '.join(MIGRATION_COLUMNS)} FROM {table} ORDER BY created_at, event_id"


def decode_event_row(row: tuple[Any, ...]) -> MigrationEvent:
    values: dict[str, Any] = dict(zip(MIGRATION_COLUMNS, row, strict=False))
    created_at: datetime = decode_event_timestamp(values["created_at"])
    return MigrationEvent(
        event_id=str(values["event_id"]),
        target_name=optional_text(values["target_name"]),
        origin_model=optional_text(values["origin_model"]),
        origin=MigrationRelation(
            database=optional_text(values["origin_database"]),
            schema=optional_text(values["origin_schema"]),
            name=str(values["origin_name"]),
        ),
        destination_model=str(values["destination_model"]),
        destination=MigrationRelation(
            database=optional_text(values["destination_database"]),
            schema=optional_text(values["destination_schema"]),
            name=str(values["destination_name"]),
        ),
        origin_version_hash=str(values["origin_version_hash"] or ""),
        discovery=MigrationDiscovery(str(values["discovery"])),
        decision=MigrationDecision(str(values["decision"])),
        run_id=str(values["run_id"]),
        created_at=created_at,
    )


def _event_values(event: MigrationEvent) -> tuple[object | None, ...]:
    return (
        event.event_id,
        event.target_name,
        event.origin_model,
        event.origin.database,
        event.origin.schema,
        event.origin.name,
        event.destination_model,
        event.destination.database,
        event.destination.schema,
        event.destination.name,
        event.origin_version_hash,
        event.discovery.value,
        event.decision.value,
        event.run_id,
        event.created_at,
    )


def decode_event_timestamp(raw: object) -> datetime:
    """Decode a stored event timestamp as an aware UTC datetime."""

    created_at: datetime = raw if isinstance(raw, datetime) else datetime.fromisoformat(str(raw))
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    return created_at


def optional_text(value: object | None) -> str | None:
    """Return a stored nullable text value as a string or None."""

    return None if value is None else str(value)
