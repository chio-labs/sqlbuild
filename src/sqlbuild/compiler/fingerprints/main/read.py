"""Bulk fingerprint read operations."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlbuild.compiler.fingerprints.main.shared.helpers.sql import (
    build_qualified_table_name,
    build_read_all_sql,
)
from sqlbuild.compiler.fingerprints.models import Fingerprint, FingerprintSet


def read_latest_fingerprints(
    *,
    connection: Any,
    execute: Any,
    database: str | None,
    schema: str,
) -> FingerprintSet:
    """Read all fingerprints for a schema and resolve latest per model in memory."""

    qualified_name: str = build_qualified_table_name(database=database, schema=schema)
    if not _table_exists(connection=connection, execute=execute, qualified_name=qualified_name):
        return FingerprintSet(schema=schema, fingerprints={})

    read_sql: str = build_read_all_sql(database=database, schema=schema)
    result: Any = execute(connection, read_sql)
    rows: list[tuple[Any, ...]] = result.fetchall()
    latest: dict[str, Fingerprint] = {}
    row: tuple[Any, ...]
    for row in rows:
        fingerprint: Fingerprint = _row_to_fingerprint(row)
        model_name: str = fingerprint.model_name
        if model_name not in latest or fingerprint.ts > latest[model_name].ts:
            latest[model_name] = fingerprint
    return FingerprintSet(schema=schema, fingerprints=latest)


def _table_exists(*, connection: Any, execute: Any, qualified_name: str) -> bool:
    """Check whether the fingerprint table exists without raising on missing."""

    try:
        execute(connection, f"SELECT 1 FROM {qualified_name} LIMIT 0")
        return True
    except Exception:
        return False


def _row_to_fingerprint(row: tuple[Any, ...]) -> Fingerprint:
    raw_ts: Any = row[9]
    ts: datetime = raw_ts if isinstance(raw_ts, datetime) else datetime.fromisoformat(str(raw_ts))
    raw_ast_hash: Any = row[6]
    ast_hash: str | None = str(raw_ast_hash) if raw_ast_hash is not None else None
    raw_target_database: Any = row[1]
    raw_target_schema: Any = row[2]
    raw_target_name: Any = row[3]
    return Fingerprint(
        model_name=str(row[0]),
        target_database=str(raw_target_database) if raw_target_database is not None else None,
        target_schema=str(raw_target_schema) if raw_target_schema is not None else None,
        target_name=str(raw_target_name) if raw_target_name is not None else None,
        run_id=str(row[4]),
        query_hash=str(row[5]),
        ast_hash=ast_hash,
        schema_fingerprint=str(row[7]),
        query_sql=str(row[8]),
        ts=ts,
    )
