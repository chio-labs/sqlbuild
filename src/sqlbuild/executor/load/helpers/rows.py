"""Returned-row normalization helpers for source loaders."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from datetime import date, datetime
from decimal import Decimal

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
    *, rows: tuple[dict[str, object], ...], columns: tuple[SourceColumnEntry, ...]
) -> str:
    """Build a VALUES-backed SELECT for framework-managed loader rows."""

    column_names: tuple[str, ...] = _resolve_column_names(rows=rows, columns=columns)
    if not column_names:
        raise ExecutorInputError("Source loader returned no rows and source declares no columns")
    declared_types: dict[str, str] = {
        column.name: column.type for column in columns if column.type is not None
    }
    if not rows:
        projections: str = ", ".join(
            f"CAST(NULL AS {declared_types.get(column_name, 'VARCHAR')}) AS {column_name}"
            for column_name in column_names
        )
        return f"SELECT {projections} WHERE 1 = 0"
    values_sql: str = ", ".join(
        "(" + ", ".join(_sql_literal(row.get(column_name)) for column_name in column_names) + ")"
        for row in rows
    )
    column_sql: str = ", ".join(column_names)
    select_sql: str = ", ".join(
        _projection_sql(column_name=column_name, declared_types=declared_types)
        for column_name in column_names
    )
    return f"SELECT {select_sql} FROM (VALUES {values_sql}) AS __loader_rows({column_sql})"


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


def _projection_sql(*, column_name: str, declared_types: dict[str, str]) -> str:
    declared_type: str | None = declared_types.get(column_name)
    if declared_type is None:
        return column_name
    return f"CAST({column_name} AS {declared_type}) AS {column_name}"


def _sql_literal(value: object) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int | float | Decimal):
        return str(value)
    if isinstance(value, datetime | date):
        return _quote_sql_string(value.isoformat())
    if isinstance(value, dict | list):
        return _quote_sql_string(json.dumps(value, sort_keys=True))
    return _quote_sql_string(str(value))


def _quote_sql_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"
