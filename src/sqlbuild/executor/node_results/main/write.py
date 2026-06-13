"""Runtime node result write operations."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlbuild.adapter.shared.types import FrameworkType
from sqlbuild.executor.node_results.helpers.serialization import encode_json_b64
from sqlbuild.executor.node_results.helpers.sql import build_create_table_sql, build_insert_sql
from sqlbuild.executor.node_results.models import NodeResultRecord


def write_node_result_record(
    *,
    connection: Any,
    execute: Any,
    database: str | None,
    schema: str,
    record: NodeResultRecord,
    render_qualified_name: Callable[..., str | None],
    render_framework_type: Callable[[FrameworkType], str],
    render_create_table_sql: Callable[..., str] | None = None,
    render_create_index_sqls: Callable[..., tuple[str, ...]] | None = None,
) -> None:
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
    if render_create_index_sqls is not None:
        index_sql: str
        for index_sql in render_create_index_sqls(database=database, schema=schema):
            execute(connection, index_sql)
    insert_sql: str = build_insert_sql(
        database=database,
        schema=schema,
        node_type=record.node_type,
        node_name=record.node_name,
        target_database=record.target_database,
        target_schema=record.target_schema,
        target_name=record.target_name,
        run_id=record.run_id,
        status=record.status,
        payload_json_b64=encode_json_b64(
            record.payload,
            label="payload",
            node_name=record.node_name,
        ),
        metadata_json_b64=encode_json_b64(
            record.metadata,
            label="metadata",
            node_name=record.node_name,
        ),
        error_message=record.error_message,
        materialized=record.materialized,
        ts=record.ts.isoformat(),
        render_qualified_name=render_qualified_name,
    )
    execute(connection, insert_sql)
