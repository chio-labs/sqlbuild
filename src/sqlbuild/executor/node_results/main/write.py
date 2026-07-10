"""Runtime node result write operations."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlbuild.adapter.shared.types import AdapterExecute, FrameworkType
from sqlbuild.executor.node_results.helpers.ddl_lock import run_with_node_result_ddl_lock
from sqlbuild.executor.node_results.helpers.serialization import encode_json_b64
from sqlbuild.executor.node_results.helpers.sql import build_create_table_sql, build_insert_sql
from sqlbuild.executor.node_results.models import NodeResultRecord


def write_node_result_record(
    *,
    connection: Any,
    execute: AdapterExecute[Any, Any],
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

    def initialize_node_result_table() -> None:
        _ = execute(connection, sql=create_sql)
        if render_create_index_sqls is not None:
            index_sql: str
            for index_sql in render_create_index_sqls(database=database, schema=schema):
                _ = execute(connection, sql=index_sql)

    _ = run_with_node_result_ddl_lock(initialize_node_result_table)
    insert_sql: str = build_insert_sql(
        database=database,
        schema=schema,
        record=record,
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
        render_qualified_name=render_qualified_name,
    )
    _ = execute(connection, sql=insert_sql)
