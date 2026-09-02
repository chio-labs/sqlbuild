from __future__ import annotations

from typing import Any

import duckdb
import pytest

from sqlbuild.adapter.contract.classes.observed_connection import ObservedConnection
from sqlbuild.adapter.contract.classes.observed_cursor import ObservedCursor
from tests.unit.src.sqlbuild.adapter.contract.classes.observed_cursor._test_types import (
    DuckDbConnectionProxyCase,
    ProxyCompatibilityCase,
)


class _PymssqlCursor:
    def __init__(self, *, connection: _RawConnection, rows: tuple[tuple[int, str], ...]) -> None:
        self.connection: _RawConnection = connection
        self._iterator: Any = iter(rows)

    def __iter__(self) -> _PymssqlCursor:
        return self

    def __next__(self) -> tuple[int, str]:
        return next(self._iterator)


class _RawConnection:
    def __init__(self, *, rows: tuple[tuple[int, str], ...]) -> None:
        self.row_factory: object | None = None
        self.autocommit = False
        self.commit_count = 0
        self.rollback_count = 0
        self._rows: tuple[tuple[int, str], ...] = rows

    def cursor(self) -> _PymssqlCursor:
        return _PymssqlCursor(connection=self, rows=self._rows)

    def commit(self) -> None:
        self.commit_count += 1

    def rollback(self) -> None:
        self.rollback_count += 1


@pytest.mark.parametrize(
    "test_case",
    [
        ProxyCompatibilityCase(
            description="connection attribute assignment",
            expected_row_factory="dict-row-factory",
            expected_autocommit=True,
            expected_rows=((1, "first"), (2, "second")),
            expected_commit_count=1,
            expected_rollback_count=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_connection_proxy_when_assigning_driver_attributes_then_raw_connection_is_updated(
    test_case: ProxyCompatibilityCase,
) -> None:
    raw_connection: _RawConnection = _RawConnection(rows=test_case.expected_rows)
    connection: ObservedConnection = ObservedConnection(
        raw_connection=raw_connection, adapter="postgres"
    )

    connection.row_factory = test_case.expected_row_factory
    connection.autocommit = test_case.expected_autocommit

    assert raw_connection.row_factory == test_case.expected_row_factory
    assert raw_connection.autocommit is test_case.expected_autocommit
    assert "row_factory" not in vars(connection)
    assert "autocommit" not in vars(connection)


@pytest.mark.parametrize(
    "test_case",
    [
        ProxyCompatibilityCase(
            description="pymssql self iterator",
            expected_row_factory="dict-row-factory",
            expected_autocommit=True,
            expected_rows=((1, "first"), (2, "second")),
            expected_commit_count=1,
            expected_rollback_count=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_pymssql_shaped_cursor_when_iterating_proxy_then_proxy_preserves_iterator_protocol(
    test_case: ProxyCompatibilityCase,
) -> None:
    raw_connection: _RawConnection = _RawConnection(rows=test_case.expected_rows)
    cursor: ObservedCursor = ObservedCursor(raw_cursor=raw_connection.cursor(), adapter="sqlserver")

    iterator: Any = iter(cursor)
    rows: tuple[tuple[int, str], ...] = tuple(iterator)

    assert iterator is cursor
    assert rows == test_case.expected_rows
    with pytest.raises(StopIteration):
        next(cursor)


@pytest.mark.parametrize(
    "test_case",
    [
        ProxyCompatibilityCase(
            description="cursor observed connection owner",
            expected_row_factory="dict-row-factory",
            expected_autocommit=True,
            expected_rows=((1, "first"), (2, "second")),
            expected_commit_count=1,
            expected_rollback_count=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_owned_cursor_when_using_cursor_connection_then_observed_owner_delegates_transaction(
    test_case: ProxyCompatibilityCase,
) -> None:
    raw_connection: _RawConnection = _RawConnection(rows=test_case.expected_rows)
    connection: ObservedConnection = ObservedConnection(
        raw_connection=raw_connection, adapter="sqlserver"
    )
    cursor: ObservedCursor = connection.cursor()

    cursor.connection.commit()
    cursor.connection.rollback()

    assert cursor.connection is connection
    assert raw_connection.commit_count == test_case.expected_commit_count
    assert raw_connection.rollback_count == test_case.expected_rollback_count


@pytest.mark.parametrize(
    "test_case",
    [
        DuckDbConnectionProxyCase(
            description="real DuckDB connection remains self iterable",
            sql="SELECT 1",
            expected_rows=((1,),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_real_duckdb_connection_when_executing_then_proxy_iterates_result_rows(
    test_case: DuckDbConnectionProxyCase,
) -> None:
    with ObservedConnection(
        raw_connection=duckdb.connect(":memory:"), adapter="duckdb"
    ) as connection:
        rows: list[tuple[int, ...]] = list(connection.execute(test_case.sql))

    assert rows == list(test_case.expected_rows)
