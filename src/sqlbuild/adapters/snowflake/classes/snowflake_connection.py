"""Snowflake connection wrapper with statement telemetry."""

from typing import Any

from sqlbuild.adapters.snowflake._helpers.session_context import may_switch_session_database
from sqlbuild.adapters.snowflake.classes.snowflake_cursor import _SnowflakeCursor
from sqlbuild.adapters.snowflake.constants import CURRENT_DATABASE_ATTRIBUTE


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
        return _SnowflakeCursor(
            self.raw_connection.cursor(), on_executed=self._forget_changed_session_context
        )

    def _forget_changed_session_context(self, *, sql: str) -> None:
        """Drop the remembered session database once a statement may have switched it."""

        if may_switch_session_database(sql):
            _ = self.__dict__.pop(CURRENT_DATABASE_ATTRIBUTE, None)
