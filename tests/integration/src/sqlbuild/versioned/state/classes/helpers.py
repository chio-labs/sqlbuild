from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlbuild.versioned.state.classes.duckdb import DuckDbStateBackend


def open_duckdb_state_backend(*, db_path: Path) -> tuple[DuckDbStateBackend, Any]:
    backend: DuckDbStateBackend = DuckDbStateBackend()
    connection: Any = backend.connect({"database": str(db_path)})
    return backend, connection


def fetch_all(connection: Any, sql: str) -> list[tuple[Any, ...]]:
    return connection.execute(sql).fetchall()
