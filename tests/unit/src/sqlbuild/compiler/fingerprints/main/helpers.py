from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlbuild.compiler.fingerprints.helpers.sql import build_read_latest_sql
from sqlbuild.compiler.fingerprints.models import Fingerprint


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


class FlakyFingerprintWriteExecute:
    def __init__(self, *, failing_create_attempts: int, error_message: str) -> None:
        self._failing_create_attempts: int = failing_create_attempts
        self._error_message: str = error_message
        self.create_attempts: int = 0
        self.executed_sql: list[str] = []

    def __call__(self, connection: Any, sql: str) -> None:
        del connection
        self.executed_sql.append(sql)
        if sql.startswith("CREATE TABLE"):
            self.create_attempts += 1
            if self.create_attempts <= self._failing_create_attempts:
                raise RuntimeError(self._error_message)


class RecordingSleeper:
    def __init__(self) -> None:
        self.sleep_seconds: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.sleep_seconds.append(seconds)


def build_write_test_fingerprint(*, node_name: str = "orders") -> Fingerprint:
    return Fingerprint(
        node_type="model",
        node_name=node_name,
        target_database=None,
        target_schema="main",
        target_name=node_name,
        run_id="run_001",
        definition_hash="definition_hash",
        version_hash="version_hash",
        schema_fingerprint="schema_hash",
        definition="SELECT 1",
        metadata_json="{}",
        ts=datetime(2026, 1, 15, 12, 0, 0),
    )


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
