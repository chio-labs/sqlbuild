"""Compare DuckDB VARIANT outputs as VARIANT values, not as JSON text."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.classes.duckdb_backed_adapter import DuckDbBackedAdapter
from sqlbuild.adapter.contract.models import ColumnInfo
from sqlbuild.adapter.relations.types import RelationLocation
from sqlbuild.executor.scenario.constants import LOCAL_TYPE_VARIANT, VARIANT_COMPARISON_TEMPLATE


def variant_compared_columns(
    *,
    adapter: BaseAdapter,
    connection: Any,
    location: RelationLocation,
    compared_columns: tuple[str, ...] | None,
) -> tuple[str, ...] | None:
    """The compared columns, a DuckDB actual relation's VARIANT columns compared as VARIANT."""

    if compared_columns is None or not isinstance(adapter, DuckDbBackedAdapter):
        return compared_columns
    actual: tuple[ColumnInfo, ...] = adapter.get_columns(
        connection=connection,
        database=location.database,
        schema=location.schema,
        name=location.name,
    )
    variants: frozenset[str] = frozenset(
        column.name.lower()
        for column in actual
        if column.type.strip().upper() == LOCAL_TYPE_VARIANT
    )
    return tuple(
        VARIANT_COMPARISON_TEMPLATE.format(column=column) if column.lower() in variants else column
        for column in compared_columns
    )
