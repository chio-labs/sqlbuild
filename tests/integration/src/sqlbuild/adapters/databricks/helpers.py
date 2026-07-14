"""Shared helpers for Databricks integration tests."""

from __future__ import annotations

import os
import re
import uuid
from pathlib import Path
from typing import Any

import pytest

from sqlbuild.adapter.classes.statement_recorder import StatementRecorder
from sqlbuild.adapters.databricks.classes.databricks_adapter import DatabricksAdapter

_ENV_KEYS: tuple[str, ...] = (
    "SQB_TEST_DATABRICKS_SERVER_HOSTNAME",
    "SQB_TEST_DATABRICKS_HTTP_PATH",
    "SQB_TEST_DATABRICKS_TOKEN",
    "SQB_TEST_DATABRICKS_CATALOG",
)


def build_databricks_connection_config(*, schema: str | None = None) -> dict[str, object]:
    """Return Databricks connection config from required env vars or skip."""

    missing: list[str] = [key for key in _ENV_KEYS if not os.environ.get(key)]
    if missing:
        pytest.skip("Databricks credentials not configured: " + ", ".join(sorted(missing)))
    return {
        "server_hostname": os.environ["SQB_TEST_DATABRICKS_SERVER_HOSTNAME"],
        "http_path": os.environ["SQB_TEST_DATABRICKS_HTTP_PATH"],
        "token": os.environ["SQB_TEST_DATABRICKS_TOKEN"],
        "catalog": os.environ["SQB_TEST_DATABRICKS_CATALOG"],
        "schema": schema,
    }


def build_unique_schema_name(*, prefix: str) -> str:
    """Build a Databricks-safe unique schema name."""

    normalized_prefix: str = re.sub(r"[^A-Za-z0-9_]", "_", prefix).lower().strip("_")
    suffix: str = uuid.uuid4().hex[:10].lower()
    return f"{normalized_prefix}_{suffix}"


def qualified_name(*, catalog: str, schema: str, name: str) -> str:
    """Build a fully qualified Databricks relation name."""

    return f"`{catalog}`.`{schema}`.`{name}`"


def execute_statements(
    *, adapter: DatabricksAdapter, connection: Any, statements: tuple[str, ...]
) -> None:
    """Execute a sequence of SQL statements against Databricks."""

    statement: str
    for statement in statements:
        adapter.execute(connection=connection, sql=statement)


def fetch_rows(
    *, adapter: DatabricksAdapter, connection: Any, sql: str
) -> tuple[tuple[object, ...], ...]:
    """Fetch all rows for a query."""

    cursor: Any = adapter.execute(connection=connection, sql=sql)
    try:
        return tuple(tuple(row) for row in cursor.fetchall())
    finally:
        cursor.close()


def write_seed_file(*, tmp_path: Path, filename: str, contents: str) -> Path:
    """Write a seed CSV file for Databricks adapter tests."""

    file_path: Path = tmp_path / filename
    file_path.write_text(contents, encoding="utf-8")
    return file_path


def build_statement_recorder() -> StatementRecorder:
    """Build a statement recorder for adapter mutation operations."""

    return StatementRecorder()
