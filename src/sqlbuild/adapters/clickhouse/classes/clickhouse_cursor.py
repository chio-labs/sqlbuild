"""DB-API shaped cursor over one fully read ClickHouse result."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import Any


class ClickHouseCursor:
    """A DB-API shaped cursor over one fully read ClickHouse result."""

    def __init__(
        self,
        *,
        column_names: Sequence[str],
        column_types: Sequence[str],
        rows: Sequence[Sequence[Any]],
        rowcount: int,
        query_id: str,
    ) -> None:
        self.description: tuple[tuple[str, str, None, None, None, None, None], ...] | None = (
            tuple(
                (name, type_name, None, None, None, None, None)
                for name, type_name in zip(column_names, column_types, strict=True)
            )
            if column_names
            else None
        )
        self._rows: list[tuple[Any, ...]] = [tuple(row) for row in rows]
        self._index: int = 0
        self.rowcount: int = rowcount
        self.query_id: str = query_id

    def fetchone(self) -> tuple[Any, ...] | None:
        if self._index >= len(self._rows):
            return None
        row: tuple[Any, ...] = self._rows[self._index]
        self._index += 1
        return row

    def fetchmany(self, size: int = 1) -> list[tuple[Any, ...]]:
        rows: list[tuple[Any, ...]] = self._rows[self._index : self._index + size]
        self._index += len(rows)
        return rows

    def fetchall(self) -> list[tuple[Any, ...]]:
        rows: list[tuple[Any, ...]] = self._rows[self._index :]
        self._index = len(self._rows)
        return rows

    def close(self) -> None:
        self._rows = []

    def __iter__(self) -> Iterator[tuple[Any, ...]]:
        while (row := self.fetchone()) is not None:
            yield row
