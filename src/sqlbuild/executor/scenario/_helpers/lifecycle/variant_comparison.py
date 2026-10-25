"""Compare DuckDB VARIANT and JSON outputs by their canonical JSON text."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.classes.duckdb_backed_adapter import DuckDbBackedAdapter
from sqlbuild.adapter.contract.models import ColumnInfo
from sqlbuild.adapter.relations.types import RelationLocation
from sqlbuild.executor.scenario._helpers.lifecycle.canonical_json import canonical_json
from sqlbuild.executor.scenario.constants import (
    CANONICAL_JSON_FUNCTION,
    SEMI_STRUCTURED_COMPARISON_TEMPLATE,
    SEMI_STRUCTURED_LOCAL_TYPES,
)


def variant_compared_columns(
    *,
    adapter: BaseAdapter,
    connection: Any,
    location: RelationLocation,
    compared_columns: tuple[str, ...] | None,
) -> tuple[str, ...] | None:
    """The compared columns, a DuckDB actual relation's VARIANT and JSON ones canonicalised."""

    if compared_columns is None or not isinstance(adapter, DuckDbBackedAdapter):
        return compared_columns
    actual: tuple[ColumnInfo, ...] = adapter.get_columns(
        connection=connection,
        database=location.database,
        schema=location.schema,
        name=location.name,
    )
    semi_structured: frozenset[str] = frozenset(
        column.name.lower()
        for column in actual
        if column.type.strip().upper() in SEMI_STRUCTURED_LOCAL_TYPES
    )
    canonicalised: tuple[str, ...] = tuple(
        SEMI_STRUCTURED_COMPARISON_TEMPLATE.format(column=column)
        if column.lower() in semi_structured
        else column
        for column in compared_columns
    )
    if canonicalised != compared_columns:
        _register_canonical_json(adapter=adapter, connection=connection)
    return canonicalised


def _register_canonical_json(*, adapter: DuckDbBackedAdapter, connection: Any) -> None:
    registered: object = adapter.execute(
        connection=connection,
        sql=(
            "SELECT COUNT(*) FROM duckdb_functions() "
            f"WHERE function_name = '{CANONICAL_JSON_FUNCTION}'"
        ),
    ).fetchone()
    if registered is not None and registered[0] == 0:
        connection.create_function(CANONICAL_JSON_FUNCTION, canonical_json, ["VARCHAR"], "VARCHAR")
