"""Public standard source freshness latest-read SQL rendering entrypoint."""

from __future__ import annotations

from collections.abc import Callable

from sqlbuild.compiler.source_freshness.main.shared.helpers.sql import (
    build_read_latest_sql as _build_read_latest_sql,
)


def build_read_latest_sql(
    *, database: str | None, schema: str, render_qualified_name: Callable[..., str | None]
) -> str:
    """Build source freshness latest-read SQL through the public entrypoint."""

    return _build_read_latest_sql(
        database=database,
        schema=schema,
        render_qualified_name=render_qualified_name,
    )
