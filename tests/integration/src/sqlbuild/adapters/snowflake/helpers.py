"""Shared helpers for Snowflake integration tests."""

from __future__ import annotations

import os
import re
import uuid
from pathlib import Path
from typing import Any

import pytest

from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.adapters.snowflake.client import SnowflakeAdapter

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


def build_snowflake_connection_config(*, schema: str | None = None) -> dict[str, object]:
    """Return Snowflake connection config from required env vars or skip."""

    missing: list[str] = [key for key in _ENV_KEYS if not os.environ.get(key)]
    if missing:
        pytest.skip("Snowflake credentials not configured: " + ", ".join(sorted(missing)))
    return {
        "account": os.environ["SQB_TEST_SNOWFLAKE_ACCOUNT"],
        "user": os.environ["SQB_TEST_SNOWFLAKE_USER"],
        "authenticator": os.environ["SQB_TEST_SNOWFLAKE_AUTHENTICATOR"],
        "token": os.environ["SQB_TEST_SNOWFLAKE_PAT"],
        "role": os.environ["SQB_TEST_SNOWFLAKE_ROLE"],
        "warehouse": os.environ["SQB_TEST_SNOWFLAKE_WAREHOUSE"],
        "database": os.environ["SQB_TEST_SNOWFLAKE_DATABASE"],
        "schema": schema if schema is not None else os.environ["SQB_TEST_SNOWFLAKE_SCHEMA"],
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
