"""Portable append-only state table DDL implementations."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from sqlbuild.adapter.contract.types import FrameworkType
from sqlbuild.sql_values.types import StateSqlValueType


def render_state_table_create_sql_impl(
    *,
    qualified_name: str,
    columns: tuple[str, ...],
    column_types: Mapping[str, StateSqlValueType],
    required_columns: frozenset[str],
    render_framework_type: Callable[[FrameworkType], str],
) -> str:
    """Render create-if-missing DDL for string, integer, and text-timestamp state columns."""

    rendered_types: dict[StateSqlValueType, str] = {
        StateSqlValueType.STRING: render_framework_type(FrameworkType.STRING),
        StateSqlValueType.INTEGER: render_framework_type(FrameworkType.INTEGER),
        StateSqlValueType.TEXT_TIMESTAMP: render_framework_type(FrameworkType.TIMESTAMP),
    }
    definitions: list[str] = []
    for column in columns:
        required: str = " NOT NULL" if column in required_columns else ""
        definitions.append(f"{column} {rendered_types[column_types[column]]}{required}")
    return f"CREATE TABLE IF NOT EXISTS {qualified_name} ({', '.join(definitions)})"
