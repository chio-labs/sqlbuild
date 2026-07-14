"""Public source freshness insert rendering operation."""

from collections.abc import Callable

from sqlbuild.adapter._helpers.source_freshness import (
    render_insert_source_freshness_records_sql as _render_sql,
)
from sqlbuild.compiler.source_freshness.models import SourceFreshnessRecord


def render_insert_source_freshness_records_sql(
    *,
    database: str | None,
    schema: str,
    records: tuple[SourceFreshnessRecord, ...],
    render_qualified_name: Callable[..., str | None],
) -> str:
    """Render DML that appends source freshness records."""

    return _render_sql(
        database=database,
        schema=schema,
        records=records,
        render_qualified_name=render_qualified_name,
    )
