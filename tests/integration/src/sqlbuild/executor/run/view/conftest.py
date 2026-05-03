from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from sqlbuild.integrations.duckdb.client import DuckDbAdapter


@pytest.fixture
def adapter() -> DuckDbAdapter:
    return DuckDbAdapter()


@pytest.fixture
def connection(adapter: DuckDbAdapter) -> Iterator[Any]:
    conn: Any = adapter.connect({"database": ":memory:"})
    conn.execute("CREATE SCHEMA test_schema")
    yield conn
    adapter.close(conn)
