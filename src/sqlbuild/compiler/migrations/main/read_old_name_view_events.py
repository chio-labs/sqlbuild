"""Read append-only old-name view facts from one schema."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from sqlbuild._native import decode_migration_event_rows, render_migration_event_read_sql
from sqlbuild.adapter.contract.types import AdapterExecute
from sqlbuild.compiler.migrations.exceptions import MigrationStateError
from sqlbuild.compiler.migrations.models import OldNameViewEvent


def read_old_name_view_events(
    *,
    connection: Any,
    execute: AdapterExecute[Any, Any],
    database: str | None,
    schema: str,
    stored_columns: Iterable[str],
    render_qualified_name: Callable[..., str | None],
) -> tuple[OldNameViewEvent, ...]:
    """Read every old-name fact this version understands from the columns the table has."""

    sql: str
    columns: tuple[str, ...]
    sql, columns = render_migration_event_read_sql(
        kind="old_name",
        database=database,
        schema=schema,
        render_qualified_name=render_qualified_name,
        stored_columns=tuple(stored_columns),
    )
    try:
        rows: list[tuple[Any, ...]] = execute(connection=connection, sql=sql).fetchall()
    except Exception as error:
        raise MigrationStateError(
            f"Unable to read old-name view facts from schema '{schema}': {error}"
        ) from error
    return decode_migration_event_rows(kind="old_name", rows=rows, columns=columns)
