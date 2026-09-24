"""Public append-only state table DDL rendering operation."""

from collections.abc import Callable, Mapping

from sqlbuild.adapter.contract.types import FrameworkType
from sqlbuild.adapter.state_sql._helpers.table_ddl import render_state_table_create_sql_impl
from sqlbuild.sql_values.types import StateSqlValueType


def render_state_table_create_sql(
    *,
    qualified_name: str,
    columns: tuple[str, ...],
    column_types: Mapping[str, StateSqlValueType],
    required_columns: frozenset[str],
    render_framework_type: Callable[[FrameworkType], str],
    transient: bool = False,
) -> str:
    """Render create-if-missing DDL for one append-only state table."""

    return render_state_table_create_sql_impl(
        qualified_name=qualified_name,
        columns=columns,
        column_types=column_types,
        required_columns=required_columns,
        render_framework_type=render_framework_type,
        transient=transient,
    )
