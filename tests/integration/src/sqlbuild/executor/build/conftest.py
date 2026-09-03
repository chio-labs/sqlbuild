from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter


@pytest.fixture
def adapter() -> DuckDbAdapter:
    return DuckDbAdapter()


@pytest.fixture
def connection(adapter: DuckDbAdapter) -> Iterator[Any]:
    conn: Any = adapter.connect({"database": ":memory:"})
    yield conn
    adapter.close(conn)


@pytest.fixture
def causal_connection(tmp_path: Path, adapter: DuckDbAdapter) -> Iterator[Any]:
    conn: Any = adapter.connect({"database": str(tmp_path / "test.duckdb")})
    yield conn
    adapter.close(conn)
