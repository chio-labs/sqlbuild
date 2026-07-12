"""Fingerprint write operations."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

from sqlbuild.adapter.types import AdapterExecute, FrameworkType
from sqlbuild.compiler.fingerprints.constants import (
    FINGERPRINT_WRITE_ATTEMPTS,
    FINGERPRINT_WRITE_RETRY_BASE_SECONDS,
)
from sqlbuild.compiler.fingerprints.helpers.sql import (
    build_create_table_sql,
    build_insert_sql,
)
from sqlbuild.compiler.fingerprints.models import Fingerprint


def write_fingerprint(
    *,
    connection: Any,
    execute: AdapterExecute[Any, Any],
    database: str | None,
    schema: str,
    fingerprint: Fingerprint,
    render_qualified_name: Callable[..., str | None],
    render_framework_type: Callable[[FrameworkType], str],
    render_create_table_sql: Callable[..., str] | None = None,
    render_create_index_sqls: Callable[..., tuple[str, ...]] | None = None,
) -> None:
    """Append one fingerprint row, retrying transient concurrent-writer conflicts."""

    create_sql: str = (
        render_create_table_sql(database=database, schema=schema)
        if render_create_table_sql is not None
        else build_create_table_sql(
            database=database,
            schema=schema,
            render_qualified_name=render_qualified_name,
            render_framework_type=render_framework_type,
        )
    )
    index_sqls: tuple[str, ...] = (
        render_create_index_sqls(database=database, schema=schema)
        if render_create_index_sqls is not None
        else ()
    )
    insert_sql: str = build_insert_sql(
        database=database,
        schema=schema,
        fingerprint=fingerprint,
        render_qualified_name=render_qualified_name,
    )
    attempt: int
    for attempt in range(FINGERPRINT_WRITE_ATTEMPTS):
        try:
            _ = _execute_write_statements(
                connection=connection,
                execute=execute,
                create_sql=create_sql,
                index_sqls=index_sqls,
                insert_sql=insert_sql,
            )
            return
        except Exception as error:
            if attempt + 1 == FINGERPRINT_WRITE_ATTEMPTS:
                raise
            _log_write_retry(fingerprint=fingerprint, attempt=attempt, error=error)
            time.sleep(FINGERPRINT_WRITE_RETRY_BASE_SECONDS * (attempt + 1))


def _execute_write_statements(
    *,
    connection: Any,
    execute: AdapterExecute[Any, Any],
    create_sql: str,
    index_sqls: tuple[str, ...],
    insert_sql: str,
) -> None:
    _ = execute(connection=connection, sql=create_sql)
    index_sql: str
    for index_sql in index_sqls:
        _ = execute(connection=connection, sql=index_sql)
    _ = execute(connection=connection, sql=insert_sql)


def _log_write_retry(*, fingerprint: Fingerprint, attempt: int, error: Exception) -> None:
    logging.getLogger("sqlbuild.fingerprints").warning(
        "fingerprint write attempt %s/%s failed for %s '%s' "
        "(likely concurrent-writer conflict); retrying: %s: %s",
        attempt + 1,
        FINGERPRINT_WRITE_ATTEMPTS,
        fingerprint.node_type,
        fingerprint.node_name,
        type(error).__name__,
        error,
    )
