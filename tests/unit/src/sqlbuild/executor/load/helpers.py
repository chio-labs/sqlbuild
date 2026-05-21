"""Helpers for source loader execution model tests."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter


class LoaderContextTestAdapter(BaseAdapter):
    """Adapter that records SQL and returns deterministic values."""

    def __init__(self) -> None:
        self.executed_sql: list[str] = []

    def connect(self, config: dict[str, object]) -> object:
        del config
        return object()

    def close(self, connection: object) -> None:
        del connection

    def execute(self, connection: Any, sql: str) -> object:
        del connection
        self.executed_sql.append(sql)
        return f"result:{sql}"
