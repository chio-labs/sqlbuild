"""Inspect which columns a stored old-name view state table has."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.migrations.constants import OLD_NAME_VIEW_TABLE_NAME


def stored_old_name_view_columns(
    *, adapter: BaseAdapter, connection: Any, database: str | None, schema: str
) -> tuple[str, ...]:
    """Return the column names of one schema's old-name view state table."""

    return tuple(
        column.name
        for column in adapter.get_columns(
            connection=connection, database=database, schema=schema, name=OLD_NAME_VIEW_TABLE_NAME
        )
    )
