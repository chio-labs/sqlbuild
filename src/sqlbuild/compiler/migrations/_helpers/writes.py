"""Idempotent append of one migration event row with bounded retries."""

from __future__ import annotations

import logging
import time
from typing import Any

from sqlbuild.adapter.contract.types import AdapterExecute
from sqlbuild.compiler.migrations.constants import MIGRATION_WRITE_RETRY_BASE_SECONDS


def append_event_row(
    *,
    connection: Any,
    execute: AdapterExecute[Any, Any],
    existing_sql: str,
    insert_sql: str,
    create_table_sql: str | None,
    attempts: int,
    subject: str,
) -> None:
    """Create the state table when given, then insert the row unless its event ID exists."""

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
                "migration event write attempt %s/%s failed for '%s'; retrying: %s",
                attempt + 1,
                attempts,
                subject,
                error,
            )
            time.sleep(MIGRATION_WRITE_RETRY_BASE_SECONDS * (attempt + 1))
