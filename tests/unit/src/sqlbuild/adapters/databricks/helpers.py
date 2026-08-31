"""Helpers for Databricks adapter unit tests."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.models import RetentionRequest
from sqlbuild.adapter.contract.types import RetentionScope


def build_retention_request(*, desired_days: int) -> RetentionRequest:
    return RetentionRequest(
        request_id="model.results",
        scope=RetentionScope.RELATION,
        database="main",
        schema="mart",
        name="results",
        desired_days=desired_days,
    )


class FakeDatabricksMetadataCursor:
    def __init__(self, *, rows: list[tuple[object, ...]] | None = None) -> None:
        self.rows: list[tuple[object, ...]] = rows or []
        self.description: tuple[tuple[str], ...] = (("format",), ("properties",))
        self.executed_sql: str | None = None
        self.closed: bool = False

    def execute(self, sql: str) -> None:
        self.executed_sql = sql

    def fetchall(self) -> list[tuple[object, ...]]:
        return self.rows

    def fetchone(self) -> tuple[object, ...] | None:
        return next(iter(self.rows), None)

    def close(self) -> None:
        self.closed = True


class FailingDatabricksMetadataCursor(FakeDatabricksMetadataCursor):
    def __init__(self, *, execute_error: Exception) -> None:
        super().__init__()
        self.execute_error = execute_error

    def execute(self, sql: str) -> None:
        self.executed_sql = sql
        raise self.execute_error


class FakeDatabricksMetadataConnection:
    def __init__(self, cursors: tuple[FakeDatabricksMetadataCursor, ...]) -> None:
        self._cursors: list[FakeDatabricksMetadataCursor] = list(cursors)
        self.returned_cursors: list[FakeDatabricksMetadataCursor] = []

    def cursor(self) -> Any:
        cursor: FakeDatabricksMetadataCursor = self._cursors.pop(0)
        self.returned_cursors.append(cursor)
        return cursor
