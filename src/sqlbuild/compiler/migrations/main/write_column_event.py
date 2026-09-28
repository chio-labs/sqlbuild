"""Append one column migration event idempotently."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlbuild.adapter.contract.types import AdapterExecute
from sqlbuild.compiler.migrations._helpers.column_sql import (
    build_column_existing_event_sql,
    build_column_insert_sql,
)
from sqlbuild.compiler.migrations._helpers.writes import append_event_row
from sqlbuild.compiler.migrations.constants import MIGRATION_WRITE_ATTEMPTS
from sqlbuild.compiler.migrations.models import ColumnMigrationEvent


def write_column_migration_event(
    *,
    connection: Any,
    execute: AdapterExecute[Any, Any],
    event: ColumnMigrationEvent,
    render_qualified_name: Callable[..., str | None],
    create_table_sql: str | None,
    attempts: int = MIGRATION_WRITE_ATTEMPTS,
) -> None:
    """Create the state table from adapter DDL when given, then insert the event if absent."""

    _ = append_event_row(
        connection=connection,
        execute=execute,
        existing_sql=build_column_existing_event_sql(
            event=event, render_qualified_name=render_qualified_name
        ),
        insert_sql=build_column_insert_sql(
            event=event, render_qualified_name=render_qualified_name
        ),
        create_table_sql=create_table_sql,
        attempts=attempts,
        subject=f"{event.model_name}.{event.destination_column}",
    )
