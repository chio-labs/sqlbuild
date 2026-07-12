"""Standard node source watermark write operations."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlbuild.adapter.shared.types import AdapterExecute
from sqlbuild.compiler.node_source_watermarks.models import NodeSourceWatermarkRecord


def write_node_source_watermark_records(
    *,
    connection: Any,
    execute: AdapterExecute[Any, Any],
    database: str | None,
    schema: str,
    records: tuple[NodeSourceWatermarkRecord, ...],
    render_create_table_sql: Callable[..., str],
    render_insert_records_sql: Callable[..., str],
    render_create_index_sqls: Callable[..., tuple[str, ...]] | None = None,
) -> None:
    """Append node source watermark rows using adapter-rendered SQL."""

    if not records:
        return
    _ = execute(
        connection=connection,
        sql=render_create_table_sql(database=database, schema=schema),
    )
    if render_create_index_sqls is not None:
        index_sql: str
        for index_sql in render_create_index_sqls(database=database, schema=schema):
            _ = execute(connection=connection, sql=index_sql)
    _ = execute(
        connection=connection,
        sql=render_insert_records_sql(database=database, schema=schema, records=records),
    )
