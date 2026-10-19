from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from sqlbuild.adapters.sqlite.classes.sqlite_adapter import SqliteAdapter


@pytest.fixture
def adapter() -> SqliteAdapter:
    return SqliteAdapter()


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    return tmp_path / "shop.sqlite"


@pytest.fixture
def connection(adapter: SqliteAdapter, database_path: Path) -> Iterator[Any]:
    conn: Any = adapter.connect({"path": str(database_path)})
    try:
        yield conn
    finally:
        adapter.close(conn)
