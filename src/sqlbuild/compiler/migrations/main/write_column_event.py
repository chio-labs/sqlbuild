"""Append one column migration event idempotently."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlbuild._native import render_migration_event_write_sql
from sqlbuild.adapter.contract.types import AdapterExecute
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

    existing_sql: str
    insert_sql: str
    existing_sql, insert_sql = render_migration_event_write_sql(
        kind="column", event=event, render_qualified_name=render_qualified_name
    )
    _ = append_event_row(
        connection=connection,
        execute=execute,
        existing_sql=existing_sql,
        insert_sql=insert_sql,
        create_table_sql=create_table_sql,
        attempts=attempts,
        subject=f"{event.model_name}.{event.destination_column}",
    )
