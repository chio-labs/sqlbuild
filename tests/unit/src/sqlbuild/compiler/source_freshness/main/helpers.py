from __future__ import annotations

from typing import Any


class FakeSourceFreshnessExecute:
    def __init__(self, *, rows: list[tuple[Any, ...]], read_error: Exception | None = None) -> None:
        self._rows: list[tuple[Any, ...]] = rows
        self._read_error: Exception | None = read_error

    def __call__(self, _connection: object, sql: str) -> Any:
        if "WHERE 1 = 0" in sql:
            return _FakeResult([])
        if self._read_error is not None:
            raise self._read_error
        return _FakeResult(self._rows)


class _FakeResult:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self._rows: list[tuple[Any, ...]] = rows

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self._rows


def render_qualified_name(*, database: str | None, schema: str | None, name: str) -> str | None:
    if schema is None:
        return None
    if database is not None:
        return f"{database}.{schema}.{name}"
    return f"{schema}.{name}"
