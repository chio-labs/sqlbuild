from __future__ import annotations

from collections.abc import Callable
from types import MappingProxyType
from typing import Any

from sqlbuild.adapter.contract.models import ColumnInfo


class StubCursor:
    def __init__(
        self,
        row: tuple[object, ...] | None = None,
        rows: list[tuple[object, ...]] | None = None,
    ) -> None:
        self._row: tuple[object, ...] | None = row
        self._rows: list[tuple[object, ...]] = rows or []

    def fetchone(self) -> tuple[object, ...] | None:
        return self._row

    def fetchall(self) -> list[tuple[object, ...]]:
        return self._rows

    def close(self) -> None:
        return None


def fake_schema_diff_describe_relation(
    connection: object,
    relation: str,
) -> tuple[ColumnInfo, ...]:
    del connection
    relation_columns: dict[str, tuple[ColumnInfo, ...]] = {
        "left_relation": (
            ColumnInfo(name="id", type="INT64"),
            ColumnInfo(name="status", type="STRING"),
        ),
        "right_relation": (
            ColumnInfo(name="id", type="STRING"),
            ColumnInfo(name="new_col", type="DATE"),
        ),
    }
    return relation_columns[relation]


def fake_row_diff_describe_relation(
    connection: object,
    relation: str,
) -> tuple[ColumnInfo, ...]:
    del connection, relation
    return (
        ColumnInfo(name="id", type="INT64"),
        ColumnInfo(name="val", type="STRING"),
    )


def build_row_diff_execute(executed_sql: list[str]) -> Any:
    def fake_execute(connection: object, sql: str) -> StubCursor:
        del connection
        executed_sql.append(sql)
        rows_by_query_kind: dict[tuple[bool, bool], tuple[object, ...]] = {
            (True, False): (0,),
            (False, True): (0,),
            (False, False): (3, 3, 4, 1, 1, 1, 1, 1),
        }
        return StubCursor(
            row=rows_by_query_kind[("WHERE id IS NULL" in sql, "HAVING COUNT(*) > 1" in sql)]
        )

    return fake_execute


def build_sample_rows_execute() -> Any:
    def fake_execute(connection: object, sql: str) -> StubCursor:
        del connection
        cursors_by_query_kind: dict[tuple[bool, bool, bool], StubCursor] = {
            (True, False, False): StubCursor(row=(0,)),
            (False, True, False): StubCursor(row=(0,)),
            (False, False, True): StubCursor(rows=[(1,)]),
            (False, False, False): StubCursor(rows=[(1, "a", "x")]),
        }
        return cursors_by_query_kind[
            (
                "WHERE id IS NULL" in sql,
                "HAVING COUNT(*) > 1" in sql,
                "__right.id IS NULL" in sql,
            )
        ]

    return fake_execute


def build_count_rows_execute(executed_sql: list[str]) -> Any:
    def fake_execute(connection: object, sql: str) -> StubCursor:
        del connection
        executed_sql.append(sql)
        return StubCursor(row=(2,))

    return fake_execute


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
    def __init__(self, rows: FakeBigQueryRows, *, statement_type: str | None = "SELECT") -> None:
        self._rows: FakeBigQueryRows = rows
        self.statement_type: str | None = statement_type

    def result(self) -> FakeBigQueryRows:
        return self._rows


class FakeBigQueryFailingJob:
    def __init__(self, error: Exception) -> None:
        self.error: Exception = error

    def result(self) -> FakeBigQueryRows:
        raise self.error


class FakeBigQueryClient:
    def __init__(
        self,
        *,
        rows: FakeBigQueryRows | None = None,
        statement_type: str | None = "SELECT",
    ) -> None:
        self.rows: FakeBigQueryRows = rows or FakeBigQueryRows(columns=(), rows=())
        self.statement_type: str | None = statement_type
        self.queries: list[tuple[str, str | None]] = []
        self.dataset_ids: list[str] = []

    def query(self, sql: str, *, location: str | None) -> FakeBigQueryJob | FakeBigQueryFailingJob:
        self.queries.append((sql, location))
        return FakeBigQueryJob(self.rows, statement_type=self.statement_type)

    def get_dataset(self, dataset_id: str) -> object:
        self.dataset_ids.append(dataset_id)
        return object()


class FakeBigQueryFailingClient(FakeBigQueryClient):
    def __init__(self, *, query_error: Exception) -> None:
        super().__init__()
        self.query_error = query_error

    def query(self, sql: str, *, location: str | None) -> FakeBigQueryFailingJob:
        self.queries.append((sql, location))
        return FakeBigQueryFailingJob(self.query_error)


class FakeBigQueryMissingDatasetClient(FakeBigQueryClient):
    def get_dataset(self, dataset_id: str) -> object:
        self.dataset_ids.append(dataset_id)
        raise FakeGoogleNotFound()


def build_fake_bigquery_schema_client(*, missing_dataset: bool) -> FakeBigQueryClient:
    client_classes: MappingProxyType[bool, Callable[[], FakeBigQueryClient]] = MappingProxyType(
        {False: FakeBigQueryClient, True: FakeBigQueryMissingDatasetClient}
    )
    return client_classes[missing_dataset]()


class FakeGoogleNotFound(Exception):
    code: int = 404


class FakeBigQueryBadRequest(Exception):
    def __init__(self, message: str, *, errors: list[dict[str, object]]) -> None:
        super().__init__(message)
        self.errors: list[dict[str, object]] = errors
