"""Driver-shaped error doubles and a recording connection for relation probe tests."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapters.bigquery.classes.bigquery_adapter import BigQueryAdapter
from sqlbuild.adapters.databricks.classes.databricks_adapter import DatabricksAdapter
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.adapters.postgres.classes.postgres_adapter import PostgresAdapter
from sqlbuild.adapters.snowflake.classes.snowflake_adapter import SnowflakeAdapter
from sqlbuild.adapters.sqlserver.classes.sqlserver_adapter import SqlServerAdapter

ADAPTERS_BY_NAME: dict[str, type[BaseAdapter]] = {
    "bigquery": BigQueryAdapter,
    "databricks": DatabricksAdapter,
    "duckdb": DuckDbAdapter,
    "postgres": PostgresAdapter,
    "snowflake": SnowflakeAdapter,
    "sqlserver": SqlServerAdapter,
}


class ProgrammingError(Exception):
    """Snowflake connector error shape carrying an errno."""

    def __init__(self, message: str, *, errno: int) -> None:
        super().__init__(message)
        self.errno: int = errno


class UndefinedTable(Exception):
    """Psycopg error shape carrying a SQLSTATE."""

    def __init__(self, message: str, *, sqlstate: str) -> None:
        super().__init__(message)
        self.sqlstate: str = sqlstate


class NotFound(Exception):
    """Google API not-found error shape."""

    code: int = 404


class Forbidden(Exception):
    """Google API permission error shape."""

    code: int = 403


class CatalogException(Exception):
    """DuckDB catalog error shape."""


class RecordingProbeConnection:
    """Connection double that records SQL and raises one configured driver error."""

    def __init__(self, *, errors: tuple[Exception, ...] = ()) -> None:
        self.errors: tuple[Exception, ...] = errors
        self.statements: list[str] = []

    def execute(self, sql: str, *args: Any, **kwargs: Any) -> object:
        del args, kwargs
        self.statements.append(sql)
        error: Exception
        for error in self.errors:
            raise error
        return object()
