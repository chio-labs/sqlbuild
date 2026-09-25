"""Create the append-only model migration table before a transactional promotion."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlbuild.adapter.contract.types import AdapterExecute, FrameworkType
from sqlbuild.compiler.migrations._helpers.sql import build_create_table_sql


def ensure_migration_table(
    *,
    connection: Any,
    execute: AdapterExecute[Any, Any],
    database: str | None,
    schema: str,
    render_qualified_name: Callable[..., str | None],
    render_framework_type: Callable[[FrameworkType], str],
    transient: bool,
) -> None:
    """Create the migration state table in one schema when it is missing."""

    _ = execute(
        connection=connection,
        sql=build_create_table_sql(
            database=database,
            schema=schema,
            render_qualified_name=render_qualified_name,
            render_framework_type=render_framework_type,
            transient=transient,
        ),
    )
