"""MotherDuck adapter implementation."""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any, ClassVar
from urllib.parse import urlencode

from sqlbuild.adapter.shared.types import LoaderLogicalType
from sqlbuild.integrations.shared.classes.duckdb import DuckDbBackedAdapter


class MotherDuckAdapter(DuckDbBackedAdapter):
    """MotherDuck adapter backed by DuckDB's MotherDuck connection support."""

    sqlglot_dialect_name: ClassVar[str | None] = "duckdb"

    def render_loader_logical_type(self, type_name: LoaderLogicalType) -> str:
        match type_name:
            case LoaderLogicalType.BOOLEAN:
                return "BOOLEAN"
            case LoaderLogicalType.INTEGER:
                return "BIGINT"
            case LoaderLogicalType.FLOAT:
                return "DOUBLE"
            case LoaderLogicalType.STRING:
                return "VARCHAR"
            case LoaderLogicalType.TIMESTAMP:
                return "TIMESTAMP"
            case LoaderLogicalType.DATE:
                return "DATE"
            case LoaderLogicalType.JSON:
                return "JSON"

    def render_loader_value_literal(
        self, *, value: object, logical_type: LoaderLogicalType | None
    ) -> str:
        if value is None:
            return "NULL"
        if isinstance(value, bool):
            return "TRUE" if value else "FALSE"
        if isinstance(value, int | float | Decimal):
            return str(value)
        if isinstance(value, datetime | date):
            return self._quote_sql_string(value.isoformat())
        if isinstance(value, dict | list):
            return self._quote_sql_string(json.dumps(value, sort_keys=True))
        return self._quote_sql_string(str(value))

    def _quote_sql_string(self, value: str) -> str:
        return "'" + value.replace("'", "''") + "'"

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
