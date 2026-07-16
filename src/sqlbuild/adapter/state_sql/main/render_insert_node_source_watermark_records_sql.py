"""Public node source watermark insert rendering operation."""

from collections.abc import Callable

from sqlbuild.adapter.state_sql._helpers.node_source_watermarks import (
    render_insert_node_source_watermark_records_sql as _render_sql,
)
from sqlbuild.compiler.node_source_watermarks.models import NodeSourceWatermarkRecord


def render_insert_node_source_watermark_records_sql(
    *,
    database: str | None,
    schema: str,
    records: tuple[NodeSourceWatermarkRecord, ...],
    render_qualified_name: Callable[..., str | None],
) -> str:
    """Render DML that appends node source watermark records."""

    return _render_sql(
        database=database,
        schema=schema,
        records=records,
        render_qualified_name=render_qualified_name,
    )
