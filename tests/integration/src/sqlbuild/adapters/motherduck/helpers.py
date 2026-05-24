"""Shared helpers for MotherDuck integration tests."""

from __future__ import annotations

import os
import uuid
from typing import Any

import pytest

from sqlbuild.adapters.motherduck.client import MotherDuckAdapter


def build_motherduck_connection_config() -> dict[str, object]:
    """Return MotherDuck connection config from env vars or skip."""

    token: str | None = os.environ.get("SQB_TEST_MOTHERDUCK_TOKEN")
    if not token:
        pytest.skip("MotherDuck credentials not configured: SQB_TEST_MOTHERDUCK_TOKEN")
    return {"token": token}


def build_unique_schema_name(*, prefix: str) -> str:
    """Build a DuckDB-safe unique schema name for MotherDuck test isolation."""

    suffix: str = uuid.uuid4().hex[:10]
    return f"{prefix}_{suffix}"


def qualified_name(*, schema: str, name: str) -> str:
    """Build a schema-qualified MotherDuck relation name."""

    return f"{schema}.{name}"


def fetch_rows(
    *, adapter: MotherDuckAdapter, connection: Any, sql: str
) -> tuple[tuple[object, ...], ...]:
    """Fetch rows from MotherDuck using the configured test credentials."""

    cursor: Any = adapter.execute(connection, sql)
    return tuple(tuple(row) for row in cursor.fetchall())
