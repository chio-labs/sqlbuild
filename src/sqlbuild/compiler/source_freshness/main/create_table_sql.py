"""Public standard source freshness table DDL rendering entrypoint."""

from __future__ import annotations

from collections.abc import Callable

from sqlbuild.adapter.shared.types import FrameworkType
from sqlbuild.compiler.source_freshness.main.shared.helpers.sql import (
    build_create_table_sql as _build_create_table_sql,
)


def build_create_table_sql(
    *,
    database: str | None,
    schema: str,
    render_qualified_name: Callable[..., str | None],
    render_framework_type: Callable[[FrameworkType], str],
    transient: bool = False,
) -> str:
    """Build source freshness table DDL through the public entrypoint."""

    return _build_create_table_sql(
        database=database,
        schema=schema,
        render_qualified_name=render_qualified_name,
        render_framework_type=render_framework_type,
        transient=transient,
    )
