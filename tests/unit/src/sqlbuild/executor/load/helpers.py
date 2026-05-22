"""Helpers for source loader execution model tests."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter


class LoaderContextTestCursor:
    def __init__(self, row: tuple[object, ...] | None) -> None:
        self._row = row

    def fetchone(self) -> tuple[object, ...] | None:
        return self._row


class LoaderContextTestAdapter(BaseAdapter):
    """Adapter that records SQL and returns deterministic values."""

    def __init__(self) -> None:
        self.executed_sql: list[str] = []

    def connect(self, config: dict[str, object]) -> object:
        del config
        return object()

    def close(self, connection: object) -> None:
        del connection

    def relation_exists(
        self,
        connection: Any,
        *,
        database: str | None,
        schema: str | None,
        name: str,
    ) -> bool:
        del connection, database, schema, name
        return True

    def execute(self, connection: Any, sql: str) -> object:
        del connection
        self.executed_sql.append(sql)
        if sql.startswith("SELECT MAX"):
            return LoaderContextTestCursor(("max-value",))
        return f"result:{sql}"
