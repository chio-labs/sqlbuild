from __future__ import annotations

from typing import Any


class FakeBigQuerySchemaField:
    def __init__(self, name: str) -> None:
        self.name: str = name


class FakeBigQueryRow:
    def __init__(self, values: tuple[object, ...]) -> None:
        self._values: tuple[object, ...] = values

    def values(self) -> tuple[object, ...]:
        return self._values


class FakeBigQueryRows:
    def __init__(self, *, columns: tuple[str, ...], rows: tuple[tuple[object, ...], ...]) -> None:
        self.schema: tuple[FakeBigQuerySchemaField, ...] = tuple(
            FakeBigQuerySchemaField(column) for column in columns
        )
        self._rows: tuple[FakeBigQueryRow, ...] = tuple(FakeBigQueryRow(row) for row in rows)

    def __iter__(self) -> Any:
        return iter(self._rows)


class FakeBigQueryJob:
    def __init__(self, rows: FakeBigQueryRows) -> None:
        self._rows: FakeBigQueryRows = rows

    def result(self) -> FakeBigQueryRows:
        return self._rows


class FakeBigQueryClient:
    def __init__(
        self, *, rows: FakeBigQueryRows | None = None, missing_dataset: bool = False
    ) -> None:
        self.rows: FakeBigQueryRows = rows or FakeBigQueryRows(columns=(), rows=())
        self.missing_dataset: bool = missing_dataset
        self.queries: list[tuple[str, str | None]] = []
        self.dataset_ids: list[str] = []

    def query(self, sql: str, *, location: str | None) -> FakeBigQueryJob:
        self.queries.append((sql, location))
        return FakeBigQueryJob(self.rows)

    def get_dataset(self, dataset_id: str) -> object:
        self.dataset_ids.append(dataset_id)
        if self.missing_dataset:
            raise FakeGoogleNotFound()
        return object()


class FakeGoogleNotFound(Exception):
    code: int = 404
