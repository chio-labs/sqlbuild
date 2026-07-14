"""Shared helpers for MotherDuck integration tests."""

from __future__ import annotations

import os
import uuid
from collections.abc import Callable
from types import MappingProxyType
from typing import Any

import pytest

from sqlbuild.adapters.motherduck.classes.motherduck_adapter import MotherDuckAdapter


def _skip_missing_token(token: str | None) -> None:
    del token
    pytest.skip("MotherDuck credentials not configured: SQB_TEST_MOTHERDUCK_TOKEN")


def _accept_token(token: str | None) -> None:
    del token


_TOKEN_VALIDATORS: MappingProxyType[bool, Callable[[str | None], None]] = MappingProxyType(
    {False: _skip_missing_token, True: _accept_token}
)


def build_motherduck_connection_config() -> dict[str, object]:
    """Return MotherDuck connection config from env vars or skip."""

    token: str | None = os.environ.get("SQB_TEST_MOTHERDUCK_TOKEN")
    _TOKEN_VALIDATORS[bool(token)](token)
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

    cursor: Any = adapter.execute(connection=connection, sql=sql)
    return tuple(tuple(row) for row in cursor.fetchall())
