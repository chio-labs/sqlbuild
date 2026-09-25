"""Append one model migration event idempotently."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

from sqlbuild.adapter.contract.types import AdapterExecute
from sqlbuild.compiler.migrations._helpers.sql import build_existing_event_sql, build_insert_sql
from sqlbuild.compiler.migrations.constants import (
    MIGRATION_WRITE_ATTEMPTS,
    MIGRATION_WRITE_RETRY_BASE_SECONDS,
)
from sqlbuild.compiler.migrations.models import MigrationEvent


def write_migration_event(
    *,
    connection: Any,
    execute: AdapterExecute[Any, Any],
    event: MigrationEvent,
    render_qualified_name: Callable[..., str | None],
    create_table_sql: str | None,
    attempts: int = MIGRATION_WRITE_ATTEMPTS,
) -> None:
    """Create the state table from adapter DDL when given, then insert the event if absent."""

    existing_sql: str = build_existing_event_sql(
        event=event, render_qualified_name=render_qualified_name
    )
    insert_sql: str = build_insert_sql(event=event, render_qualified_name=render_qualified_name)
    attempt: int
    for attempt in range(attempts):
        try:
            if create_table_sql is not None:
                _ = execute(connection=connection, sql=create_table_sql)
            if not execute(connection=connection, sql=existing_sql).fetchall():
                _ = execute(connection=connection, sql=insert_sql)
            return
        except Exception as error:
            if attempt + 1 == attempts:
                raise
            logging.getLogger("sqlbuild.migrations").warning(
                "model migration event write attempt %s/%s failed for '%s'; retrying: %s",
                attempt + 1,
                attempts,
                event.destination_model,
                error,
            )
            time.sleep(MIGRATION_WRITE_RETRY_BASE_SECONDS * (attempt + 1))
