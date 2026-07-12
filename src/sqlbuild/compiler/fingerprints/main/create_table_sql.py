"""Public fingerprint table DDL rendering entrypoint."""

from __future__ import annotations

from collections.abc import Callable

from sqlbuild.adapter.types import FrameworkType
from sqlbuild.compiler.fingerprints.helpers.sql import (
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
    """Build fingerprint-table DDL through the public fingerprint entrypoint."""

    return _build_create_table_sql(
        database=database,
        schema=schema,
        render_qualified_name=render_qualified_name,
        render_framework_type=render_framework_type,
        transient=transient,
    )
