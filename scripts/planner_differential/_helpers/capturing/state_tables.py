"""Read SQLBuild state-table rows from a project's DuckDB files."""

from __future__ import annotations

import base64
import binascii
import json
from collections import Counter
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path

import duckdb

from scripts.planner_differential._helpers.capturing.canonical import canonical_value
from scripts.planner_differential.constants import (
    BASE64_COLUMN_SUFFIX,
    DUCKDB_SUFFIX,
    STATE_TABLE_PREFIX,
)
from scripts.planner_differential.models import TextMasks

_STATE_TABLES_SQL: str = (
    "SELECT table_schema, table_name FROM information_schema.tables "
    "WHERE table_type = 'BASE TABLE' AND starts_with(table_name, ?) "
    "ORDER BY table_schema, table_name"
)


def database_files(project_dir: Path) -> tuple[Path, ...]:
    """Return the project's DuckDB files in a stable order."""

    return tuple(sorted(project_dir.rglob(f"*{DUCKDB_SUFFIX}")))


def state_rows(*, project_dir: Path, masks: TextMasks) -> dict[str, list[str]]:
    """Return each state table's masked rows as compact JSON, sorted."""

    tables: dict[str, list[str]] = {}
    for path in database_files(project_dir):
        connection: duckdb.DuckDBPyConnection = duckdb.connect(str(path), read_only=True)
        try:
            names: list[tuple[str, str]] = connection.execute(
                _STATE_TABLES_SQL, [STATE_TABLE_PREFIX]
            ).fetchall()
            for schema, table in names:
                key: str = f"{path.relative_to(project_dir).as_posix()}:{schema}.{table}"
                tables[key] = _table_rows(
                    connection=connection, relation=f'"{schema}"."{table}"', masks=masks
                )
        finally:
            connection.close()
    return tables


def state_delta(
    *, before: dict[str, list[str]], after: dict[str, list[str]]
) -> dict[str, dict[str, list[object]]]:
    """Return the rows each state table gained and lost, as decoded JSON."""

    delta: dict[str, dict[str, list[object]]] = {}
    for table in sorted({*before, *after}):
        old: Counter[str] = Counter(before.get(table, []))
        new: Counter[str] = Counter(after.get(table, []))
        added: list[str] = sorted((new - old).elements())
        removed: list[str] = sorted((old - new).elements())
        if added or removed:
            delta[table] = {
                "added": [json.loads(row) for row in added],
                "removed": [json.loads(row) for row in removed],
            }
    return delta


def _table_rows(
    *, connection: duckdb.DuckDBPyConnection, relation: str, masks: TextMasks
) -> list[str]:
    cursor: duckdb.DuckDBPyConnection = connection.execute(f"SELECT * FROM {relation}")
    columns: list[str] = [str(column[0]) for column in cursor.description or ()]
    rows: list[str] = []
    for row in cursor.fetchall():
        decoded: dict[str, object] = {
            column: _decoded(column=column, value=value)
            for column, value in zip(columns, row, strict=True)
        }
        rows.append(
            json.dumps(
                canonical_value(value=decoded, masks=masks),
                sort_keys=True,
                ensure_ascii=False,
                default=str,
            )
        )
    return sorted(rows)


def _decoded(*, column: str, value: object) -> object:
    if isinstance(value, datetime | date | time):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, str) and column.endswith(BASE64_COLUMN_SUFFIX):
        return _base64_json(value)
    return value


def _base64_json(value: str) -> object:
    try:
        text: str = base64.b64decode(value, validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        return value
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text
