"""Returned-row normalization helpers for source loaders."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date, datetime
from decimal import Decimal

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.types import LoaderLogicalType
from sqlbuild.executor.shared.exceptions import ExecutorInputError
from sqlbuild.spec.models.source import SourceColumnEntry


def normalize_loader_rows(value: object) -> tuple[dict[str, object], ...]:
    """Validate and normalize a loader return value to dict rows."""

    if value is None:
        raise ExecutorInputError("Source loaders that return nothing are not supported yet")
    if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
        raise ExecutorInputError("Source loaders must return a list or iterable of dict rows")
    rows: list[dict[str, object]] = []
    item: object
    for item in value:
        if not isinstance(item, Mapping):
            raise ExecutorInputError("Source loaders must return only dict rows")
        rows.append({str(key): row_value for key, row_value in item.items()})
    return tuple(rows)


def build_rows_sql(
    *,
    adapter: BaseAdapter,
    rows: tuple[dict[str, object], ...],
    columns: tuple[SourceColumnEntry, ...],
) -> str:
    """Build a VALUES-backed SELECT for framework-managed loader rows."""

    column_names: tuple[str, ...] = _resolve_column_names(rows=rows, columns=columns)
    if not column_names:
        raise ExecutorInputError("Source loader returned no rows and source declares no columns")
    declared_types: dict[str, str] = {
        column.name: column.type for column in columns if column.type is not None
    }
    inferred_types: dict[str, LoaderLogicalType] = _infer_column_types(rows=rows)
    if not rows:
        projections: str = ", ".join(
            _empty_projection_sql(
                adapter=adapter,
                column_name=column_name,
                declared_types=declared_types,
                inferred_types=inferred_types,
            )
            for column_name in column_names
        )
        return f"SELECT {projections} WHERE 1 = 0"
    values_sql: str = ", ".join(
        "("
        + ", ".join(
            adapter.render_loader_value_literal(
                value=row.get(column_name),
                logical_type=inferred_types.get(column_name),
            )
            for column_name in column_names
        )
        + ")"
        for row in rows
    )
    column_sql: str = ", ".join(column_names)
    select_sql: str = ", ".join(
        _projection_sql(
            adapter=adapter,
            column_name=column_name,
            declared_types=declared_types,
            inferred_types=inferred_types,
        )
        for column_name in column_names
    )
    return f"SELECT {select_sql} FROM (VALUES {values_sql}) AS __loader_rows({column_sql})"


def _empty_projection_sql(
    *,
    adapter: BaseAdapter,
    column_name: str,
    declared_types: dict[str, str],
    inferred_types: dict[str, LoaderLogicalType],
) -> str:
    sql_type: str = (
        _column_sql_type(
            adapter=adapter,
            column_name=column_name,
            declared_types=declared_types,
            inferred_types=inferred_types,
        )
        or "VARCHAR"
    )
    return f"CAST(NULL AS {sql_type}) AS {column_name}"


def _resolve_column_names(
    *, rows: tuple[dict[str, object], ...], columns: tuple[SourceColumnEntry, ...]
) -> tuple[str, ...]:
    names: list[str] = [column.name for column in columns]
    row: dict[str, object]
    for row in rows:
        key: str
        for key in row:
            if key not in names:
                names.append(key)
    return tuple(names)


def _projection_sql(
    *,
    adapter: BaseAdapter,
    column_name: str,
    declared_types: dict[str, str],
    inferred_types: dict[str, LoaderLogicalType],
) -> str:
    sql_type: str | None = _column_sql_type(
        adapter=adapter,
        column_name=column_name,
        declared_types=declared_types,
        inferred_types=inferred_types,
    )
    if sql_type is None:
        return column_name
    return f"CAST({column_name} AS {sql_type}) AS {column_name}"


def _column_sql_type(
    *,
    adapter: BaseAdapter,
    column_name: str,
    declared_types: dict[str, str],
    inferred_types: dict[str, LoaderLogicalType],
) -> str | None:
    declared_type: str | None = declared_types.get(column_name)
    if declared_type is not None:
        return declared_type
    inferred_type: LoaderLogicalType | None = inferred_types.get(column_name)
    if inferred_type is None:
        return None
    return adapter.render_loader_logical_type(inferred_type)


def _infer_column_types(rows: tuple[dict[str, object], ...]) -> dict[str, LoaderLogicalType]:
    inferred: dict[str, LoaderLogicalType] = {}
    row: dict[str, object]
    for row in rows:
        column_name: str
        value: object
        for column_name, value in row.items():
            logical_type: LoaderLogicalType | None = _infer_value_type(value)
            if logical_type is None:
                continue
            previous_type: LoaderLogicalType | None = inferred.get(column_name)
            if previous_type is not None and previous_type != logical_type:
                raise ExecutorInputError(
                    f"Source loader returned conflicting types for column '{column_name}'"
                )
            inferred[column_name] = logical_type
    return inferred


def _infer_value_type(value: object) -> LoaderLogicalType | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return LoaderLogicalType.BOOLEAN
    if isinstance(value, int):
        return LoaderLogicalType.INTEGER
    if isinstance(value, float | Decimal):
        return LoaderLogicalType.FLOAT
    if isinstance(value, str):
        return LoaderLogicalType.STRING
    if isinstance(value, datetime):
        return LoaderLogicalType.TIMESTAMP
    if isinstance(value, date):
        return LoaderLogicalType.DATE
    if isinstance(value, dict | list):
        return LoaderLogicalType.JSON
    return LoaderLogicalType.STRING
