"""Helpers for source loader execution model tests."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.classes.base_adapter import BaseAdapter


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
        return {
            True: LoaderContextTestCursor(("max-value",)),
            False: f"result:{sql}",
        }[sql.startswith("SELECT MAX")]


class CountingLoaderContextTestAdapter(LoaderContextTestAdapter):
    """Adapter that records connection attempts."""

    def __init__(self) -> None:
        super().__init__()
        self.connection_count: int = 0

    def connect(self, config: dict[str, object]) -> object:
        self.connection_count += 1
        return super().connect(config)
