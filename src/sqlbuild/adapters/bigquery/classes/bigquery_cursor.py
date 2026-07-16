"""BigQuery cursor wrapper."""

from typing import Any


class _BigQueryCursor:
    """Small cursor-like wrapper around a BigQuery RowIterator."""

    def __init__(self, rows: Any) -> None:
        self.description: tuple[tuple[str], ...] | None = None
        schema: object | None = getattr(rows, "schema", None)
        if schema:
            self.description = tuple((str(field.name),) for field in schema)
        self._rows: list[tuple[object, ...]] = [tuple(row.values()) for row in rows]
        self._index: int = 0

    def fetchone(self) -> tuple[object, ...] | None:
        if self._index >= len(self._rows):
            return None
        row: tuple[object, ...] = self._rows[self._index]
        self._index += 1
        return row

    def fetchall(self) -> list[tuple[object, ...]]:
        rows: list[tuple[object, ...]] = self._rows[self._index :]
        self._index = len(self._rows)
        return rows

    def fetchmany(self, size: int) -> list[tuple[object, ...]]:
        rows: list[tuple[object, ...]] = self._rows[self._index : self._index + size]
        self._index += len(rows)
        return rows

    def close(self) -> None:
        return None
