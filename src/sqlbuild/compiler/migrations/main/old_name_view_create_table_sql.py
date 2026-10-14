"""Old-name view state table SQL entrypoint."""

from __future__ import annotations

from collections.abc import Callable

from sqlbuild._native import render_migration_state_create_sql
from sqlbuild.adapter.contract.types import FrameworkType


def build_old_name_view_state_create_table_sql(
    *,
    database: str | None,
    schema: str,
    render_qualified_name: Callable[..., str | None],
    render_framework_type: Callable[[FrameworkType], str],
) -> str:
    """Build DDL that creates the old-name view fact table when it is missing."""

    return render_migration_state_create_sql(
        kind="old_name",
        database=database,
        schema=schema,
        render_qualified_name=render_qualified_name,
        render_framework_type=render_framework_type,
    )
