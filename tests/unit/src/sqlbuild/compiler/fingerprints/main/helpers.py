from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from types import MappingProxyType
from typing import Any

from sqlbuild.compiler.fingerprints._helpers.sql import build_read_latest_sql
from sqlbuild.compiler.fingerprints.models import Fingerprint


class FakeFingerprintResult:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self._rows: list[tuple[object, ...]] = rows

    def fetchall(self) -> list[tuple[object, ...]]:
        return self._rows


class FakeFingerprintExecute:
    def __init__(self, *, rows: list[tuple[object, ...]]) -> None:
        self._rows: list[tuple[object, ...]] = rows
        self.executed_sql: list[str] = []

    def __call__(self, connection: Any, sql: str) -> FakeFingerprintResult:
        del connection
        self.executed_sql.append(sql)
        return FakeFingerprintResult(self._rows)


class FailingFingerprintExecute(FakeFingerprintExecute):
    def __init__(self, *, read_error: Exception) -> None:
        super().__init__(rows=[])
        self._read_error = read_error

    def __call__(self, connection: Any, sql: str) -> FakeFingerprintResult:
        del connection
        self.executed_sql.append(sql)
        raise self._read_error


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
        _WRITE_ACTIONS[sql.startswith("CREATE TABLE")](self)


def _ignore_write(execute: FlakyFingerprintWriteExecute) -> None:
    del execute


def _record_create(execute: FlakyFingerprintWriteExecute) -> None:
    execute.create_attempts += 1
    _CREATE_ACTIONS[execute.create_attempts <= execute._failing_create_attempts](execute)


def _accept_create(execute: FlakyFingerprintWriteExecute) -> None:
    del execute


def _fail_create(execute: FlakyFingerprintWriteExecute) -> None:
    raise RuntimeError(execute._error_message)


_WRITE_ACTIONS: MappingProxyType[bool, Callable[[FlakyFingerprintWriteExecute], None]] = (
    MappingProxyType({False: _ignore_write, True: _record_create})
)
_CREATE_ACTIONS: MappingProxyType[bool, Callable[[FlakyFingerprintWriteExecute], None]] = (
    MappingProxyType({False: _accept_create, True: _fail_create})
)


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
    return {
        (True, False): None,
        (True, True): None,
        (False, True): f"{database}.{schema}.{name}",
        (False, False): f"{schema}.{name}",
    }[(schema is None, database is not None)]


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
