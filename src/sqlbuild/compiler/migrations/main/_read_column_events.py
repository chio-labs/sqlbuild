"""Read append-only column migration events from one schema."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlbuild._native import decode_migration_event_rows, render_migration_event_read_sql
from sqlbuild.adapter.contract.types import AdapterExecute
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

    sql: str
    columns: tuple[str, ...]
    sql, columns = render_migration_event_read_sql(
        kind="column", database=database, schema=schema, render_qualified_name=render_qualified_name
    )
    try:
        rows: list[tuple[Any, ...]] = execute(connection=connection, sql=sql).fetchall()
    except Exception as error:
        raise MigrationStateError(
            f"Unable to read column migration events from schema '{schema}': {error}"
        ) from error
    return decode_migration_event_rows(kind="column", rows=rows, columns=columns)
