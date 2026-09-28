"""Old-name view state table SQL entrypoint."""

from __future__ import annotations

from collections.abc import Callable

from sqlbuild.adapter.contract.types import FrameworkType
from sqlbuild.compiler.migrations._helpers.old_name_sql import build_old_name_create_table_sql


def build_old_name_view_state_create_table_sql(
    *,
    database: str | None,
    schema: str,
    render_qualified_name: Callable[..., str | None],
    render_framework_type: Callable[[FrameworkType], str],
    transient: bool = False,
) -> str:
    """Build DDL that creates the old-name view fact table when it is missing."""

    return build_old_name_create_table_sql(
        database=database,
        schema=schema,
        render_qualified_name=render_qualified_name,
        render_framework_type=render_framework_type,
        transient=transient,
    )
