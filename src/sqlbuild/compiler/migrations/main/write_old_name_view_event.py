"""Append one old-name view fact idempotently."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlbuild.adapter.contract.types import AdapterExecute
from sqlbuild.compiler.migrations._helpers.old_name_sql import (
    build_old_name_existing_event_sql,
    build_old_name_insert_sql,
)
from sqlbuild.compiler.migrations._helpers.writes import append_event_row
from sqlbuild.compiler.migrations.constants import MIGRATION_WRITE_ATTEMPTS
from sqlbuild.compiler.migrations.models import OldNameViewEvent


def write_old_name_view_event(
    *,
    connection: Any,
    execute: AdapterExecute[Any, Any],
    event: OldNameViewEvent,
    render_qualified_name: Callable[..., str | None],
    create_table_sql: str | None,
    attempts: int = MIGRATION_WRITE_ATTEMPTS,
) -> None:
    """Create the state table from adapter DDL when given, then insert the fact if absent."""

    _ = append_event_row(
        connection=connection,
        execute=execute,
        existing_sql=build_old_name_existing_event_sql(
            event=event, render_qualified_name=render_qualified_name
        ),
        insert_sql=build_old_name_insert_sql(
            event=event, render_qualified_name=render_qualified_name
        ),
        create_table_sql=create_table_sql,
        attempts=attempts,
        subject=f"{event.destination_model} old name {event.old.name}",
    )
