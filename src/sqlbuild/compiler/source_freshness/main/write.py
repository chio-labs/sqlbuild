"""Standard source freshness write operations."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.shared.types import AdapterExecute
from sqlbuild.compiler.source_freshness.helpers.sql import (
    build_create_table_sql,
)
from sqlbuild.compiler.source_freshness.models import (
    SourceFreshnessRecord,
    SourceFreshnessRenderers,
)


def write_source_freshness_records(
    *,
    connection: Any,
    execute: AdapterExecute[Any, Any],
    database: str | None,
    schema: str,
    records: tuple[SourceFreshnessRecord, ...],
    renderers: SourceFreshnessRenderers,
    transient: bool = False,
) -> None:
    """Append source freshness rows, creating the table once if needed."""

    if not records:
        return
    create_sql: str = (
        renderers.render_create_table_sql(database=database, schema=schema)
        if renderers.render_create_table_sql is not None
        else build_create_table_sql(
            database=database,
            schema=schema,
            render_qualified_name=renderers.render_qualified_name,
            render_framework_type=renderers.render_framework_type,
            transient=transient,
        )
    )
    _ = execute(connection=connection, sql=create_sql)
    if renderers.render_create_index_sqls is not None:
        index_sql: str
        for index_sql in renderers.render_create_index_sqls(database=database, schema=schema):
            _ = execute(connection=connection, sql=index_sql)
    _ = execute(
        connection=connection,
        sql=renderers.render_insert_records_sql(
            database=database,
            schema=schema,
            records=records,
        ),
    )
