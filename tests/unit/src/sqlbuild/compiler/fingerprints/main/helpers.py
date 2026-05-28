from __future__ import annotations

from typing import Any


class FakeFingerprintResult:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self._rows: list[tuple[object, ...]] = rows

    def fetchall(self) -> list[tuple[object, ...]]:
        return self._rows


class FakeFingerprintExecute:
    def __init__(
        self, *, rows: list[tuple[object, ...]], read_error: Exception | None = None
    ) -> None:
        self._rows: list[tuple[object, ...]] = rows
        self._read_error: Exception | None = read_error

    def __call__(self, connection: Any, sql: str) -> FakeFingerprintResult:
        del connection
        if "WHERE 1 = 0" in sql:
            return FakeFingerprintResult([])
        if self._read_error is not None:
            raise self._read_error
        return FakeFingerprintResult(self._rows)


def render_qualified_name(*, database: str | None, schema: str | None, name: str) -> str | None:
    if schema is None:
        return None
    if database is None:
        return f"{schema}.{name}"
    return f"{database}.{schema}.{name}"
