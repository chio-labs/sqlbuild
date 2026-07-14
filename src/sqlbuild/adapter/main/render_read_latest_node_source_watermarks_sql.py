"""Public node source watermark read rendering operation."""

from collections.abc import Callable

from sqlbuild.adapter._helpers.node_source_watermarks import (
    render_read_latest_node_source_watermarks_sql as _render_sql,
)


def render_read_latest_node_source_watermarks_sql(
    *,
    database: str | None,
    schema: str,
    render_qualified_name: Callable[..., str | None],
) -> str:
    """Render SQL that reads latest node source watermark rows per identity."""

    return _render_sql(
        database=database,
        schema=schema,
        render_qualified_name=render_qualified_name,
    )
