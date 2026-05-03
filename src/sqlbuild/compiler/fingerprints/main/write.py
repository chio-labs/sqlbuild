"""Fingerprint write operations."""

from __future__ import annotations

from typing import Any

from sqlbuild.compiler.fingerprints.main.shared.helpers.sql import (
    build_create_table_sql,
    build_insert_sql,
)
from sqlbuild.compiler.fingerprints.models import Fingerprint


def write_fingerprint(
    *,
    connection: Any,
    execute: Any,
    database: str | None,
    schema: str,
    fingerprint: Fingerprint,
) -> None:
    """Append one fingerprint row, creating the table if needed."""

    create_sql: str = build_create_table_sql(database=database, schema=schema)
    execute(connection, create_sql)
    insert_sql: str = build_insert_sql(
        database=database,
        schema=schema,
        model_name=fingerprint.model_name,
        run_id=fingerprint.run_id,
        query_hash=fingerprint.query_hash,
        ast_hash=fingerprint.ast_hash,
        schema_fingerprint=fingerprint.schema_fingerprint,
        query_sql=fingerprint.query_sql,
        ts=fingerprint.ts.isoformat(),
    )
    execute(connection, insert_sql)
