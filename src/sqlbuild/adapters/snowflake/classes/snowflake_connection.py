"""Snowflake connection wrapper with statement telemetry."""

from typing import Any

from sqlbuild.adapters.snowflake.classes.snowflake_cursor import _SnowflakeCursor


class _SnowflakeConnection:
    """Small wrapper exposing a DuckDB-like execute method for base adapter helpers."""

    def __init__(self, raw_connection: Any) -> None:
        self.raw_connection: Any = raw_connection

    def execute(self, sql: str, *, statement_params: dict[str, str] | None = None) -> Any:
        kwargs: dict[str, object] = {}
        if statement_params is not None:
            kwargs["_statement_params"] = statement_params
        return self.cursor().execute(sql, **kwargs)

    def close(self) -> None:
        self.raw_connection.close()

    def cursor(self) -> _SnowflakeCursor:
        return _SnowflakeCursor(self.raw_connection.cursor())
