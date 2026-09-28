"""Shared fakes for adapter unit tests."""

from __future__ import annotations

from collections.abc import Callable
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
    """A connection that records SQL, answers every query with fixed rows, and names a project."""

    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self.rows: list[tuple[object, ...]] = rows
        self.executed: list[str] = []
        self.location: str = "US"
        self.client: GrantClient = GrantClient()

    def execute(self, sql: str) -> GrantRows:
        """Record the SQL and return the fixed rows."""

        self.executed.append(sql)
        return GrantRows(self.rows)


class GrantClient:
    """The BigQuery client attribute of a fake connection."""

    project: str = "orders-project"


def grant_execute(connection: GrantConnection) -> Callable[..., GrantRows]:
    """Return an adapter execute stub that routes SQL to a recording connection."""

    def execute(*, connection: Any, sql: str) -> GrantRows:
        return connection.execute(sql)

    del connection
    return execute
