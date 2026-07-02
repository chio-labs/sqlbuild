from __future__ import annotations

from typing import Any

from sqlbuild.compiler.fingerprints.helpers.sql import build_read_latest_sql


class FakeFingerprintResult:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self._rows: list[tuple[object, ...]] = rows

    def fetchall(self) -> list[tuple[object, ...]]:
        return self._rows


class FakeFingerprintExecute:
    def __init__(
        self, *, rows: list[tuple[object, ...]], read_error: Exception | None = None
    ) -> None:
        self._rows: list[tuple[object, ...]] = rows
        self._read_error: Exception | None = read_error
        self.executed_sql: list[str] = []

    def __call__(self, connection: Any, sql: str) -> FakeFingerprintResult:
        del connection
        self.executed_sql.append(sql)
        if self._read_error is not None:
            raise self._read_error
        return FakeFingerprintResult(self._rows)


class FakeFingerprintWriteExecute:
    def __init__(self) -> None:
        self.executed_sql: list[str] = []

    def __call__(self, connection: Any, sql: str) -> None:
        del connection
        self.executed_sql.append(sql)


def render_qualified_name(*, database: str | None, schema: str | None, name: str) -> str | None:
    if schema is None:
        return None
    if database is None:
        return f"{schema}.{name}"
    return f"{database}.{schema}.{name}"


def render_read_latest_sql(*, database: str | None, schema: str) -> str:
    return build_read_latest_sql(
        database=database,
        schema=schema,
        render_qualified_name=render_qualified_name,
    )


def render_sentinel_read_latest_sql(*, database: str | None, schema: str) -> str:
    del database, schema
    return "SELECT 'sentinel latest fingerprint sql'"


def render_create_fingerprint_index_sqls(*, database: str | None, schema: str) -> tuple[str, ...]:
    del database, schema
    return ("CREATE INDEX sentinel_fingerprint_idx",)
