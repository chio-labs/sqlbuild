"""Fingerprint write operations."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlbuild.adapter.shared.types import FrameworkType
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
    render_qualified_name: Callable[..., str | None],
    render_framework_type: Callable[[FrameworkType], str],
    render_create_table_sql: Callable[..., str] | None = None,
) -> None:
    """Append one fingerprint row, creating the table if needed."""

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
    execute(connection, create_sql)
    insert_sql: str = build_insert_sql(
        database=database,
        schema=schema,
        model_name=fingerprint.model_name,
        target_database=fingerprint.target_database,
        target_schema=fingerprint.target_schema,
        target_name=fingerprint.target_name,
        run_id=fingerprint.run_id,
        query_hash=fingerprint.query_hash,
        schema_fingerprint=fingerprint.schema_fingerprint,
        query_sql=fingerprint.query_sql,
        metadata_json=fingerprint.metadata_json,
        ts=fingerprint.ts.isoformat(),
        render_qualified_name=render_qualified_name,
    )
    execute(connection, insert_sql)
