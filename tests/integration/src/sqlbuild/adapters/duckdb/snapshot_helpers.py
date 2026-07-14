from __future__ import annotations

from typing import Any

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter


class InsertFaultDuckDbAdapter(DuckDbAdapter):
    """DuckDB adapter that fails when inserting into a configured snapshot target."""

    def __init__(self, *, fault_target: str) -> None:
        self.fault_target = fault_target

    def execute(self, connection: Any, sql: str) -> Any:
        if sql.startswith(f"INSERT INTO {self.fault_target} "):
            raise RuntimeError("injected snapshot insert failure")
        return super().execute(connection=connection, sql=sql)
