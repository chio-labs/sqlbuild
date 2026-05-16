"""Shared helpers for Postgres integration tests."""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any

import pytest

from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.integrations.postgres.client import PostgresAdapter

_ENV_KEYS: tuple[str, ...] = (
    "SQB_TEST_POSTGRES_HOST",
    "SQB_TEST_POSTGRES_PORT",
    "SQB_TEST_POSTGRES_DATABASE",
    "SQB_TEST_POSTGRES_USER",
    "SQB_TEST_POSTGRES_PASSWORD",
)


def build_postgres_connection_config() -> dict[str, object]:
    """Return Postgres connection config from required env vars or skip."""

    missing: list[str] = [key for key in _ENV_KEYS if not os.environ.get(key)]
    if missing:
        pytest.skip("Postgres credentials not configured: " + ", ".join(sorted(missing)))
    return {
        "host": os.environ["SQB_TEST_POSTGRES_HOST"],
        "port": int(os.environ["SQB_TEST_POSTGRES_PORT"]),
        "dbname": os.environ["SQB_TEST_POSTGRES_DATABASE"],
        "user": os.environ["SQB_TEST_POSTGRES_USER"],
        "password": os.environ["SQB_TEST_POSTGRES_PASSWORD"],
    }


def build_unique_schema_name(*, prefix: str) -> str:
    """Build a Postgres-safe unique schema name for test isolation."""

    suffix: str = uuid.uuid4().hex[:10]
    return f"{prefix}_{suffix}"


def qualified_name(*, schema: str, name: str) -> str:
    """Build a two-part unquoted Postgres relation name."""

    return f"{schema}.{name}"


def execute_statements(
    *, adapter: PostgresAdapter, connection: Any, statements: tuple[str, ...]
) -> None:
    for statement in statements:
        adapter.execute(connection, statement)


def fetch_rows(
    *, adapter: PostgresAdapter, connection: Any, sql: str
) -> tuple[tuple[object, ...], ...]:
    cursor: Any = adapter.execute(connection, sql)
    return tuple(tuple(row) for row in cursor.fetchall())


def write_seed_file(*, tmp_path: Path, filename: str, contents: str) -> Path:
    file_path: Path = tmp_path / filename
    file_path.write_text(contents, encoding="utf-8")
    return file_path


def build_statement_recorder() -> StatementRecorder:
    return StatementRecorder()
