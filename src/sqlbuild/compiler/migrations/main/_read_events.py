"""Read append-only model migration events from one schema."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlbuild._native import decode_migration_event_rows, render_migration_event_read_sql
from sqlbuild.adapter.contract.types import AdapterExecute
from sqlbuild.compiler.migrations.exceptions import MigrationStateError
from sqlbuild.compiler.migrations.models import MigrationEvent


def read_migration_events(
    *,
    connection: Any,
    execute: AdapterExecute[Any, Any],
    database: str | None,
    schema: str,
    render_qualified_name: Callable[..., str | None],
) -> tuple[MigrationEvent, ...]:
    """Read every migration event recorded in one schema's state table."""

    sql: str
    columns: tuple[str, ...]
    sql, columns = render_migration_event_read_sql(
        kind="model", database=database, schema=schema, render_qualified_name=render_qualified_name
    )
    try:
        rows: list[tuple[Any, ...]] = execute(connection=connection, sql=sql).fetchall()
    except Exception as error:
        raise MigrationStateError(
            f"Unable to read model migration events from schema '{schema}': {error}"
        ) from error
    return decode_migration_event_rows(kind="model", rows=rows, columns=columns)
