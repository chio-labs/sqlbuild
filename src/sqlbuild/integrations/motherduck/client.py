"""MotherDuck adapter implementation."""

from __future__ import annotations

from typing import Any, ClassVar
from urllib.parse import urlencode

from sqlbuild.integrations.shared.classes.duckdb import DuckDbBackedAdapter


class MotherDuckAdapter(DuckDbBackedAdapter):
    """MotherDuck adapter backed by DuckDB's MotherDuck connection support."""

    sqlglot_dialect_name: ClassVar[str | None] = "duckdb"

    def connect(self, config: dict[str, Any]) -> Any:
        """Open a MotherDuck connection using DuckDB's md: connection string."""

        duckdb_config: dict[str, Any] = dict(config)
        duckdb_config["database"] = self._connection_database(config)
        return super().connect(duckdb_config)

    def default_schema(self) -> str:
        """MotherDuck uses DuckDB's main schema by default."""

        return "main"

    def _connection_database(self, config: dict[str, Any]) -> str:
        raw_database: object | None = config.get("database")
        database: str = "md:" if raw_database is None else str(raw_database)
        if database == "":
            database = "md:"
        elif not database.startswith("md:"):
            database = f"md:{database}"

        token: object | None = config.get("token")
        if token is None or str(token) == "":
            return database

        separator: str = "&" if "?" in database else "?"
        return f"{database}{separator}{urlencode({'motherduck_token': str(token)})}"
