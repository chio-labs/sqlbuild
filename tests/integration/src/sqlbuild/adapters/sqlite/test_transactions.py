from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any

import pytest

from sqlbuild.adapter.contract.models import ColumnInfo
from sqlbuild.adapters.sqlite.classes.sqlite_adapter import SqliteAdapter
from tests.integration.src.sqlbuild.adapters.sqlite._test_types import (
    SqliteInterruptTestCase,
    SqliteMergeCountTestCase,
    SqliteReadOnlyPathTestCase,
    SqliteRetypeIndexTestCase,
)
from tests.integration.src.sqlbuild.adapters.sqlite.helpers import (
    create_orders,
    fetch_rows,
    recorder,
    run_sql,
)

_LARGE_INSERT_SQL: str = (
    "INSERT INTO orders (order_id) WITH RECURSIVE ids(n) AS "
    "(SELECT 10 UNION ALL SELECT n + 1 FROM ids WHERE n < 200000000) SELECT n FROM ids"
)


@pytest.mark.parametrize(
    "test_case",
    [
        SqliteInterruptTestCase(
            description="an interrupted INSERT inside a transaction re-raises the interrupt",
            interrupt_after_seconds=0.3,
            expected_error_fragment="interrupted",
            expected_rows=((1,), (2,), (3,)),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_interrupt_during_transaction_when_rolling_back_then_sqlite_keeps_original_error(
    test_case: SqliteInterruptTestCase, adapter: SqliteAdapter, connection: Any
) -> None:
    create_orders(adapter=adapter, connection=connection, relation="orders")
    timer: threading.Timer = threading.Timer(
        test_case.interrupt_after_seconds, adapter.interrupt_connection, args=(connection,)
    )

    timer.start()
    with pytest.raises(sqlite3.OperationalError) as raised, adapter.transaction(connection):
        adapter.execute(connection=connection, sql="DELETE FROM orders WHERE order_id = 1")
        adapter.execute(connection=connection, sql=_LARGE_INSERT_SQL)
    timer.join()

    assert test_case.expected_error_fragment in str(raised.value)
    assert not connection.in_transaction()
    assert (
        fetch_rows(
            adapter=adapter, connection=connection, sql="SELECT order_id FROM orders ORDER BY 1"
        )
        == test_case.expected_rows
    )


@pytest.mark.parametrize(
    "test_case",
    [
        SqliteMergeCountTestCase(
            description="merge reports updated and inserted rows together",
            source_sql=(
                "SELECT 1 AS order_id, 11 AS customer_id, 1 AS amount, "
                "'2026-01-05 00:00:00' AS ordered_at, 'shipped' AS status "
                "UNION ALL SELECT 4, 40, 2, '2026-01-05 00:00:00', 'placed'"
            ),
            expected_affected=2,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_matched_and_new_keys_when_merging_then_sqlite_counts_both(
    test_case: SqliteMergeCountTestCase, adapter: SqliteAdapter, connection: Any
) -> None:
    create_orders(adapter=adapter, connection=connection, relation="orders")

    affected: int | None = adapter.merge(
        connection=connection,
        destination="orders",
        sql=test_case.source_sql,
        unique_key="order_id",
        statement_recorder=recorder(),
    )

    assert affected == test_case.expected_affected


@pytest.mark.parametrize(
    "test_case",
    [
        SqliteReadOnlyPathTestCase(
            description="read-only paths with URI characters open the named file",
            file_name="orders ?#%.sqlite",
            expected_rows=((1,),),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_uri_characters_in_path_when_opening_read_only_then_sqlite_reads_the_file(
    test_case: SqliteReadOnlyPathTestCase, adapter: SqliteAdapter, tmp_path: Path
) -> None:
    path: str = str(tmp_path / test_case.file_name)
    writer: Any = adapter.connect({"path": path})
    run_sql(
        adapter=adapter,
        connection=writer,
        statements=("CREATE TABLE orders (order_id INTEGER)", "INSERT INTO orders VALUES (1)"),
    )
    adapter.close(writer)

    reader: Any = adapter.connect({"path": path, "read_only": True})
    rows: tuple[tuple[object, ...], ...] = fetch_rows(
        adapter=adapter, connection=reader, sql="SELECT order_id FROM orders"
    )
    adapter.close(reader)

    assert rows == test_case.expected_rows
    assert all(entry.name.startswith(test_case.file_name) for entry in tmp_path.iterdir())


@pytest.mark.parametrize(
    "test_case",
    [
        SqliteRetypeIndexTestCase(
            description="a table rebuilt for new column types keeps its indexes",
            expected_indexes=(
                ("orders_customer_idx", "CREATE INDEX orders_customer_idx ON orders (customer_id)"),
                (
                    "orders_status_idx",
                    "CREATE UNIQUE INDEX orders_status_idx ON orders (order_id, status)",
                ),
            ),
            expected_columns=(
                ColumnInfo("order_id", "INTEGER"),
                ColumnInfo("customer_id", "TEXT"),
                ColumnInfo("amount", "NUMERIC"),
                ColumnInfo("ordered_at", "TIMESTAMP"),
                ColumnInfo("status", "VARCHAR(16)"),
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_indexed_table_when_altering_column_types_then_sqlite_recreates_indexes(
    test_case: SqliteRetypeIndexTestCase, adapter: SqliteAdapter, connection: Any
) -> None:
    create_orders(adapter=adapter, connection=connection, relation="orders")
    run_sql(
        adapter=adapter,
        connection=connection,
        statements=(
            "CREATE INDEX orders_customer_idx ON orders (customer_id)",
            "CREATE UNIQUE INDEX orders_status_idx ON orders (order_id, status)",
        ),
    )

    adapter.alter_column_types(
        connection=connection,
        destination="orders",
        columns=(ColumnInfo("customer_id", "TEXT"),),
        statement_recorder=recorder(),
    )

    assert (
        fetch_rows(
            adapter=adapter,
            connection=connection,
            sql=(
                "SELECT name, sql FROM sqlite_schema WHERE type = 'index' "
                "AND tbl_name = 'orders' ORDER BY name"
            ),
        )
        == test_case.expected_indexes
    )
    assert (
        adapter.describe_relation(connection=connection, relation="orders")
        == test_case.expected_columns
    )
