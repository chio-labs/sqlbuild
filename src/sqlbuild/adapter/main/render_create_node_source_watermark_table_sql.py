"""Public node source watermark table rendering operation."""

from collections.abc import Callable

from sqlbuild.adapter.helpers.node_source_watermarks import (
    render_create_node_source_watermark_table_sql as _render_sql,
)
from sqlbuild.adapter.types import FrameworkType


def render_create_node_source_watermark_table_sql(
    *,
    database: str | None,
    schema: str,
    render_qualified_name: Callable[..., str | None],
    render_framework_type: Callable[[FrameworkType], str],
    transient: bool = False,
) -> str:
    """Render DDL that creates the node source watermark table."""

    return _render_sql(
        database=database,
        schema=schema,
        render_qualified_name=render_qualified_name,
        render_framework_type=render_framework_type,
        transient=transient,
    )
