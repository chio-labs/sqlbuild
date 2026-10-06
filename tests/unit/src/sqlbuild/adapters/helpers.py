"""Shared fakes for adapter unit tests."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any


class FetchedRows:
    """A cursor result that returns fixed rows."""

    def __init__(self, rows: list[tuple[str, str]]) -> None:
        self._rows: list[tuple[str, str]] = rows

    def fetchall(self) -> list[tuple[str, str]]:
        """Return the fixed rows."""

        return self._rows


def recording_execute(
    *, rows: list[tuple[str, str]], executed: list[str]
) -> Callable[..., FetchedRows]:
    """Return an adapter execute stub that records SQL and returns fixed rows."""

    def execute(*, connection: Any, sql: str) -> FetchedRows:
        del connection
        executed.append(sql)
        return FetchedRows(rows)

    return execute


class GrantRows:
    """A cursor result that returns fixed grant rows of any width."""

    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self._rows: list[tuple[object, ...]] = rows

    def fetchall(self) -> list[tuple[object, ...]]:
        """Return the fixed rows."""

        return self._rows


class GrantConnection:
    """A connection that records SQL, answers queries in order, and names a project."""

    def __init__(self, answers: tuple[list[tuple[object, ...]], ...]) -> None:
        self.answers: Iterator[list[tuple[object, ...]]] = iter(answers)
        self.executed: list[str] = []
        self.location: str = "US"
        self.client: GrantClient = GrantClient()

    def execute(self, sql: str) -> GrantRows:
        """Record the SQL and return the next answer, or no rows once they run out."""

        self.executed.append(sql)
        return GrantRows(next(self.answers, []))


class GrantClient:
    """The BigQuery client attribute of a fake connection."""

    project: str = "orders-project"


def grant_execute(connection: GrantConnection) -> Callable[..., GrantRows]:
    """Return an adapter execute stub that routes SQL to a recording connection."""

    def execute(*, connection: Any, sql: str) -> GrantRows:
        return connection.execute(sql)

    del connection
    return execute


class MetadataCursor:
    """A cursor that records metadata SQL and returns fixed rows."""

    def __init__(self, *, rows: tuple[tuple[object, ...], ...], executed: list[str]) -> None:
        self._rows: tuple[tuple[object, ...], ...] = rows
        self._executed: list[str] = executed

    def execute(self, sql: str, params: tuple[object, ...] | None = None) -> MetadataCursor:
        self._executed.append(f"{sql} {params or ()}")
        return self

    def fetchone(self) -> tuple[object, ...] | None:
        return next(iter(self._rows), None)

    def fetchall(self) -> list[tuple[object, ...]]:
        return list(self._rows)

    def close(self) -> None:
        return None


class MetadataConnection:
    """A connection whose cursors share one SQL log and fixed rows."""

    def __init__(self, rows: tuple[tuple[object, ...], ...]) -> None:
        self.rows: tuple[tuple[object, ...], ...] = rows
        self.executed: list[str] = []

    def cursor(self) -> MetadataCursor:
        return MetadataCursor(rows=self.rows, executed=self.executed)


@dataclass(frozen=True)
class FakeBigQueryTable:
    """BigQuery tables API metadata."""

    table_type: str
    num_rows: int | None


class FakeBigQueryClient:
    """BigQuery client that records requested table ids."""

    def __init__(self, table: FakeBigQueryTable) -> None:
        self.table: FakeBigQueryTable = table
        self.requested: list[str] = []

    def get_table(self, table_id: str) -> FakeBigQueryTable:
        self.requested.append(table_id)
        return self.table


@dataclass(frozen=True)
class FakeBigQueryConnection:
    """BigQuery connection holding a fake client."""

    client: FakeBigQueryClient


def execute_through_cursor(*, connection: MetadataConnection, sql: str) -> MetadataCursor:
    """Adapter execute stub that runs SQL on a fresh fake cursor."""

    return connection.cursor().execute(sql)
