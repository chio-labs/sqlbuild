"""Append one model migration event idempotently."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

from sqlbuild.adapter.contract.types import AdapterExecute, FrameworkType
from sqlbuild.compiler.migrations._helpers.sql import build_create_table_sql, build_insert_sql
from sqlbuild.compiler.migrations.constants import (
    MIGRATION_WRITE_ATTEMPTS,
    MIGRATION_WRITE_RETRY_BASE_SECONDS,
)
from sqlbuild.compiler.migrations.exceptions import MigrationStateError
from sqlbuild.compiler.migrations.models import MigrationEvent


def write_migration_event(
    *,
    connection: Any,
    execute: AdapterExecute[Any, Any],
    event: MigrationEvent,
    render_qualified_name: Callable[..., str | None],
    render_framework_type: Callable[[FrameworkType], str],
    transient: bool,
) -> None:
    """Create the state table when missing and insert the event unless already present."""

    if event.destination.schema is None:
        raise MigrationStateError("model migration events require a destination schema")
    statements: tuple[str, ...] = (
        build_create_table_sql(
            database=event.destination.database,
            schema=event.destination.schema,
            render_qualified_name=render_qualified_name,
            render_framework_type=render_framework_type,
            transient=transient,
        ),
        build_insert_sql(event=event, render_qualified_name=render_qualified_name),
    )
    attempt: int
    for attempt in range(MIGRATION_WRITE_ATTEMPTS):
        try:
            statement: str
            for statement in statements:
                _ = execute(connection=connection, sql=statement)
            return
        except Exception as error:
            if attempt + 1 == MIGRATION_WRITE_ATTEMPTS:
                raise
            logging.getLogger("sqlbuild.migrations").warning(
                "model migration event write attempt %s/%s failed for '%s'; retrying: %s",
                attempt + 1,
                MIGRATION_WRITE_ATTEMPTS,
                event.destination_model,
                error,
            )
            time.sleep(MIGRATION_WRITE_RETRY_BASE_SECONDS * (attempt + 1))
