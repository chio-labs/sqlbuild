"""Shared helpers for Snowflake integration tests."""

from __future__ import annotations

import os
import re
import uuid
from collections.abc import Callable
from pathlib import Path
from types import MappingProxyType
from typing import Any, cast

import pytest

from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.adapters.snowflake.classes.snowflake_adapter import SnowflakeAdapter

_ENV_KEYS: tuple[str, ...] = (
    "SQB_TEST_SNOWFLAKE_ACCOUNT",
    "SQB_TEST_SNOWFLAKE_USER",
    "SQB_TEST_SNOWFLAKE_AUTHENTICATOR",
    "SQB_TEST_SNOWFLAKE_PAT",
    "SQB_TEST_SNOWFLAKE_ROLE",
    "SQB_TEST_SNOWFLAKE_WAREHOUSE",
    "SQB_TEST_SNOWFLAKE_DATABASE",
    "SQB_TEST_SNOWFLAKE_SCHEMA",
)


def _missing_env_key(key: str) -> tuple[str, ...]:
    return (key,)


def _present_env_key(key: str) -> tuple[str, ...]:
    del key
    return ()


def _skip_missing_env(missing: tuple[str, ...]) -> None:
    pytest.skip("Snowflake credentials not configured: " + ", ".join(sorted(missing)))


def _accept_env(missing: tuple[str, ...]) -> None:
    del missing


def _configured_schema(schema: str | None) -> str:
    return cast(str, schema)


def _default_schema(schema: str | None) -> str:
    del schema
    return os.environ["SQB_TEST_SNOWFLAKE_SCHEMA"]


_ENV_KEY_RESULTS: MappingProxyType[bool, Callable[[str], tuple[str, ...]]] = MappingProxyType(
    {False: _missing_env_key, True: _present_env_key}
)
_ENV_VALIDATORS: MappingProxyType[bool, Callable[[tuple[str, ...]], None]] = MappingProxyType(
    {False: _accept_env, True: _skip_missing_env}
)
_SCHEMA_BUILDERS: MappingProxyType[bool, Callable[[str | None], str]] = MappingProxyType(
    {False: _configured_schema, True: _default_schema}
)


def build_snowflake_connection_config(*, schema: str | None = None) -> dict[str, object]:
    """Return Snowflake connection config from required env vars or skip."""

    missing: tuple[str, ...] = sum(
        (_ENV_KEY_RESULTS[bool(os.environ.get(key))](key) for key in _ENV_KEYS),
        (),
    )
    _ENV_VALIDATORS[bool(missing)](missing)
    return {
        "account": os.environ["SQB_TEST_SNOWFLAKE_ACCOUNT"],
        "user": os.environ["SQB_TEST_SNOWFLAKE_USER"],
        "authenticator": os.environ["SQB_TEST_SNOWFLAKE_AUTHENTICATOR"],
        "token": os.environ["SQB_TEST_SNOWFLAKE_PAT"],
        "role": os.environ["SQB_TEST_SNOWFLAKE_ROLE"],
        "warehouse": os.environ["SQB_TEST_SNOWFLAKE_WAREHOUSE"],
        "database": os.environ["SQB_TEST_SNOWFLAKE_DATABASE"],
        "schema": _SCHEMA_BUILDERS[schema is None](schema),
    }


def build_unique_schema_name(*, prefix: str) -> str:
    """Build a Snowflake-safe unique schema name."""

    normalized_prefix: str = re.sub(r"[^A-Za-z0-9_]", "_", prefix).upper().strip("_")
    suffix: str = uuid.uuid4().hex[:10].upper()
    return f"{normalized_prefix}_{suffix}"


def qualified_name(*, database: str, schema: str, name: str) -> str:
    """Build a three-part unquoted Snowflake relation name."""

    return f"{database}.{schema}.{name}"


def execute_statements(
    *, adapter: SnowflakeAdapter, connection: Any, statements: tuple[str, ...]
) -> None:
    """Execute a sequence of SQL statements against Snowflake."""

    statement: str
    for statement in statements:
        adapter.execute(connection=connection, sql=statement)


def fetch_rows(
    *, adapter: SnowflakeAdapter, connection: Any, sql: str
) -> tuple[tuple[object, ...], ...]:
    """Fetch all rows for a query."""

    cursor: Any = adapter.execute(connection=connection, sql=sql)
    try:
        return tuple(tuple(row) for row in cursor.fetchall())
    finally:
        cursor.close()


def create_schema_if_missing(*, schema: str) -> None:
    """Create a Snowflake schema for real-warehouse tests."""

    adapter: SnowflakeAdapter = SnowflakeAdapter()
    config: dict[str, object] = build_snowflake_connection_config()
    database_name: str = str(config["database"])
    connection: Any = adapter.connect(config)
    try:
        adapter.execute(
            connection=connection, sql=f"CREATE SCHEMA IF NOT EXISTS {database_name}.{schema}"
        )
    finally:
        adapter.close(connection)


def write_seed_file(*, tmp_path: Path, filename: str, contents: str) -> Path:
    """Write a seed CSV file for Snowflake adapter tests."""

    file_path: Path = tmp_path / filename
    file_path.write_text(contents, encoding="utf-8")
    return file_path


def build_statement_recorder() -> StatementRecorder:
    """Build a statement recorder for adapter mutation operations."""

    return StatementRecorder()


class RecordingSnowflakeAdapter(SnowflakeAdapter):
    """Snowflake adapter recording statements executed through the adapter seam."""

    def __init__(self) -> None:
        self.statement_recorder = StatementRecorder()

    def _execute(self, *, connection: Any, sql: str) -> Any:
        self.statement_recorder.record(sql)
        return super()._execute(connection=connection, sql=sql)
