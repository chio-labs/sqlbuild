"""Read append-only old-name view facts from one schema."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlbuild.adapter.contract.types import AdapterExecute
from sqlbuild.compiler.migrations._helpers.old_name_sql import (
    build_old_name_read_sql,
    decode_old_name_event_row,
)
from sqlbuild.compiler.migrations.exceptions import MigrationStateError
from sqlbuild.compiler.migrations.models import OldNameViewEvent


def read_old_name_view_events(
    *,
    connection: Any,
    execute: AdapterExecute[Any, Any],
    database: str | None,
    schema: str,
    render_qualified_name: Callable[..., str | None],
) -> tuple[OldNameViewEvent, ...]:
    """Read every old-name fact this version understands; unknown event types are skipped."""

    sql: str = build_old_name_read_sql(
        database=database, schema=schema, render_qualified_name=render_qualified_name
    )
    try:
        rows: list[tuple[Any, ...]] = execute(connection=connection, sql=sql).fetchall()
    except Exception as error:
        raise MigrationStateError(
            f"Unable to read old-name view facts from schema '{schema}': {error}"
        ) from error
    events: list[OldNameViewEvent] = []
    row: tuple[Any, ...]
    for row in rows:
        event: OldNameViewEvent | None = decode_old_name_event_row(tuple(row))
        if event is not None:
            events.append(event)
    return tuple(events)
