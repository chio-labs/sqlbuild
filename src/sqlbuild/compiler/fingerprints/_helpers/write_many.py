"""Bounded append-only fingerprint batch writes."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence
from typing import Any

import sqlbuild._native as _native
from sqlbuild.adapter.contract.types import AdapterExecute, FrameworkType
from sqlbuild.compiler.fingerprints._helpers.sql import (
    build_create_table_sql,
    build_qualified_table_name,
)
from sqlbuild.compiler.fingerprints.constants import (
    FINGERPRINT_WRITE_ATTEMPTS,
    FINGERPRINT_WRITE_BATCH_MAX_BYTES,
    FINGERPRINT_WRITE_BATCH_SIZE,
    FINGERPRINT_WRITE_RETRY_BASE_SECONDS,
)
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.fingerprints.types import FingerprintWriteProgress


def write_fingerprints_impl(
    *,
    connection: Any,
    execute: AdapterExecute[Any, Any],
    database: str | None,
    schema: str,
    fingerprints: Sequence[Fingerprint],
    render_qualified_name: Callable[..., str | None],
    render_framework_type: Callable[[FrameworkType], str],
    render_create_table_sql: Callable[..., str] | None,
    render_create_index_sqls: Callable[..., tuple[str, ...]] | None,
    on_progress: FingerprintWriteProgress | None,
) -> None:
    if not fingerprints:
        return
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
    _ = _execute_with_retry(
        connection=connection,
        execute=execute,
        sqls=(create_sql, *index_sqls),
        fingerprints=fingerprints,
    )
    batches: list[tuple[tuple[Fingerprint, ...], str]] = _native.fingerprint_insert_batches(
        build_qualified_table_name(
            database=database,
            schema=schema,
            render_qualified_name=render_qualified_name,
        ),
        list(fingerprints),
        (FINGERPRINT_WRITE_BATCH_SIZE, FINGERPRINT_WRITE_BATCH_MAX_BYTES),
    )
    completed_count: int = 0
    batch: tuple[Fingerprint, ...]
    insert_sql: str
    for batch, insert_sql in batches:
        _ = _execute_with_retry(
            connection=connection,
            execute=execute,
            sqls=(insert_sql,),
            fingerprints=batch,
        )
        completed_count += len(batch)
        if on_progress is not None:
            on_progress(completed=completed_count, total=len(fingerprints))


def _execute_with_retry(
    *,
    connection: Any,
    execute: AdapterExecute[Any, Any],
    sqls: Sequence[str],
    fingerprints: Sequence[Fingerprint],
) -> None:
    attempt: int
    for attempt in range(FINGERPRINT_WRITE_ATTEMPTS):
        try:
            sql: str
            for sql in sqls:
                _ = execute(connection=connection, sql=sql)
            return
        except Exception as error:
            if attempt + 1 == FINGERPRINT_WRITE_ATTEMPTS:
                raise
            _log_write_retry(fingerprints=fingerprints, attempt=attempt, error=error)
            time.sleep(FINGERPRINT_WRITE_RETRY_BASE_SECONDS * (attempt + 1))


def _log_write_retry(
    *, fingerprints: Sequence[Fingerprint], attempt: int, error: Exception
) -> None:
    first: Fingerprint = fingerprints[0]
    logging.getLogger("sqlbuild.fingerprints").warning(
        "fingerprint batch write attempt %s/%s failed for %s row(s), starting with %s '%s' "
        "(likely concurrent-writer conflict); retrying: %s: %s",
        attempt + 1,
        FINGERPRINT_WRITE_ATTEMPTS,
        len(fingerprints),
        first.node_type,
        first.node_name,
        type(error).__name__,
        error,
    )
