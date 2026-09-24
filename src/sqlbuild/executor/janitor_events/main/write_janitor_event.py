"""Janitor audit event warehouse write operation."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlbuild.adapter.contract.types import AdapterExecute
from sqlbuild.executor.janitor_events._helpers.sql import (
    build_existing_event_sql,
    build_insert_sql,
)
from sqlbuild.executor.janitor_events.models import JanitorEventRecord


def write_janitor_event_record(
    *,
    connection: Any,
    execute: AdapterExecute[Any, Any],
    record: JanitorEventRecord,
    render_qualified_name: Callable[..., str | None],
) -> bool:
    """Append one janitor event unless its deterministic ID was already written."""

    cursor: Any = execute(
        connection=connection,
        sql=build_existing_event_sql(record=record, render_qualified_name=render_qualified_name),
    )
    if cursor.fetchall():
        return False
    _ = execute(
        connection=connection,
        sql=build_insert_sql(record=record, render_qualified_name=render_qualified_name),
    )
    return True
