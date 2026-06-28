"""Standard source freshness write operations."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlbuild.adapter.shared.types import FrameworkType
from sqlbuild.compiler.source_freshness.main.shared.helpers.sql import (
    build_create_table_sql,
    build_insert_sql,
)
from sqlbuild.compiler.source_freshness.models import SourceFreshnessRecord


def write_source_freshness_records(
    *,
    connection: Any,
    execute: Any,
    database: str | None,
    schema: str,
    records: tuple[SourceFreshnessRecord, ...],
    render_qualified_name: Callable[..., str | None],
    render_framework_type: Callable[[FrameworkType], str],
    render_create_table_sql: Callable[..., str] | None = None,
    render_create_index_sqls: Callable[..., tuple[str, ...]] | None = None,
    transient: bool = False,
) -> None:
    """Append source freshness rows, creating the table once if needed."""

    if not records:
        return
    create_sql: str = (
        render_create_table_sql(database=database, schema=schema)
        if render_create_table_sql is not None
        else build_create_table_sql(
            database=database,
            schema=schema,
            render_qualified_name=render_qualified_name,
            render_framework_type=render_framework_type,
            transient=transient,
        )
    )
    execute(connection, create_sql)
    if render_create_index_sqls is not None:
        index_sql: str
        for index_sql in render_create_index_sqls(database=database, schema=schema):
            execute(connection, index_sql)
    record: SourceFreshnessRecord
    for record in records:
        insert_sql: str = build_insert_sql(
            database=database,
            schema=schema,
            source_name=record.source_name,
            target_database=record.target_database,
            target_schema=record.target_schema,
            target_name=record.target_name,
            run_id=record.run_id,
            strategy=record.strategy,
            value_kind=record.value_kind,
            data_version=record.data_version,
            data_version_hash=record.data_version_hash,
            observed_at=record.observed_at.isoformat(),
            render_qualified_name=render_qualified_name,
        )
        execute(connection, insert_sql)
