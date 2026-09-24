"""Portable SQL for append-only model migration events."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlbuild.adapter.contract.types import FrameworkType
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
    table: str = qualified_migration_table(
        database=database, schema=schema, render_qualified_name=render_qualified_name
    )
    string_type: str = render_framework_type(FrameworkType.STRING)
    timestamp_type: str = render_framework_type(FrameworkType.TIMESTAMP)
    definitions: str = ", ".join(
        f"{column} "
        + (
            timestamp_type
            if MIGRATION_COLUMN_TYPES[column] == StateSqlValueType.TIMESTAMP
            else string_type
        )
        for column in MIGRATION_COLUMNS
    )
    table_kind: str = "TRANSIENT TABLE" if transient else "TABLE"
    return f"CREATE {table_kind} IF NOT EXISTS {table} ({definitions})"


def build_insert_sql(
    *, event: MigrationEvent, render_qualified_name: Callable[..., str | None]
) -> str:
    if event.destination.schema is None:
        raise MigrationStateError("model migration events require a destination schema")
    table: str = qualified_migration_table(
        database=event.destination.database,
        schema=event.destination.schema,
        render_qualified_name=render_qualified_name,
    )
    values: tuple[object | None, ...] = _event_values(event)
    literals: str = ", ".join(
        render_state_sql_literal(value=value, declared_type=MIGRATION_COLUMN_TYPES[column])
        for column, value in zip(MIGRATION_COLUMNS, values, strict=True)
    )
    event_id_literal: str = render_state_sql_literal(
        value=event.event_id, declared_type=StateSqlValueType.STRING
    )
    return (
        f"INSERT INTO {table} ({', '.join(MIGRATION_COLUMNS)}) SELECT {literals} "
        f"WHERE NOT EXISTS (SELECT 1 FROM {table} WHERE event_id = {event_id_literal})"
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
    raw_created_at: Any = values["created_at"]
    created_at: datetime = (
        raw_created_at
        if isinstance(raw_created_at, datetime)
        else datetime.fromisoformat(str(raw_created_at))
    )
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    return MigrationEvent(
        event_id=str(values["event_id"]),
        target_name=_optional_text(values["target_name"]),
        origin_model=_optional_text(values["origin_model"]),
        origin=MigrationRelation(
            database=_optional_text(values["origin_database"]),
            schema=_optional_text(values["origin_schema"]),
            name=str(values["origin_name"]),
        ),
        destination_model=str(values["destination_model"]),
        destination=MigrationRelation(
            database=_optional_text(values["destination_database"]),
            schema=_optional_text(values["destination_schema"]),
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


def _optional_text(value: object | None) -> str | None:
    return None if value is None else str(value)
