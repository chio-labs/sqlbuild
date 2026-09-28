"""Read append-only column migration events from one schema."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlbuild.adapter.contract.types import AdapterExecute
from sqlbuild.compiler.migrations._helpers.column_sql import (
    build_column_read_sql,
    decode_column_event_row,
)
from sqlbuild.compiler.migrations.exceptions import MigrationStateError
from sqlbuild.compiler.migrations.models import ColumnMigrationEvent


def read_column_migration_events(
    *,
    connection: Any,
    execute: AdapterExecute[Any, Any],
    database: str | None,
    schema: str,
    render_qualified_name: Callable[..., str | None],
) -> tuple[ColumnMigrationEvent, ...]:
    """Read every column migration event this version understands from one schema."""

    sql: str = build_column_read_sql(
        database=database, schema=schema, render_qualified_name=render_qualified_name
    )
    try:
        rows: list[tuple[Any, ...]] = execute(connection=connection, sql=sql).fetchall()
    except Exception as error:
        raise MigrationStateError(
            f"Unable to read column migration events from schema '{schema}': {error}"
        ) from error
    events: list[ColumnMigrationEvent] = []
    row: tuple[Any, ...]
    for row in rows:
        try:
            events.append(decode_column_event_row(tuple(row)))
        except ValueError:
            continue
    return tuple(events)
