from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter


class InsertFaultDuckDbAdapter(DuckDbAdapter):
    """DuckDB adapter that fails when inserting into a configured snapshot target."""

    def __init__(self, *, fault_target: str) -> None:
        self.fault_target = fault_target

    def _execute(self, connection: Any, sql: str) -> Any:
        executor: Callable[..., Any] = {
            False: self._execute_sql,
            True: self._raise_insert_failure,
        }[sql.startswith(f"INSERT INTO {self.fault_target} ")]
        return executor(connection=connection, sql=sql)

    def _execute_sql(self, *, connection: Any, sql: str) -> Any:
        return super()._execute(connection=connection, sql=sql)

    def _raise_insert_failure(self, *, connection: Any, sql: str) -> Any:
        del connection, sql
        raise RuntimeError("injected snapshot insert failure")
