"""Unkeyed side-only samples read a bounded result and release their cursor."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from sqlbuild.adapter.contract.constants import DIFF_LEFT_SIDE
from tests.integration.src.sqlbuild.adapters.sqlite._test_types import (
    SqliteUnkeyedSampleTestCase,
)
from tests.integration.src.sqlbuild.adapters.sqlite.helpers import (
    RecordingCursorSqliteAdapter,
    recorder,
)


@pytest.mark.parametrize(
    "test_case",
    [
        SqliteUnkeyedSampleTestCase(
            description="many distinct side-only rows stop at the limit",
            left_sql=(
                "SELECT 1 AS order_id UNION ALL SELECT 2 UNION ALL SELECT 3 "
                "UNION ALL SELECT 4 UNION ALL SELECT 5"
            ),
            limit=2,
            expected_row_count=2,
            expected_order_ids=frozenset({1, 2, 3, 4, 5}),
        ),
        SqliteUnkeyedSampleTestCase(
            description="a repeated side-only row fills the limit by multiplicity",
            left_sql="SELECT 7 AS order_id UNION ALL SELECT 7 UNION ALL SELECT 7",
            limit=2,
            expected_row_count=2,
            expected_order_ids=frozenset({7}),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_side_only_rows_when_sampling_unkeyed_then_query_is_bounded_and_cursor_closed(
    test_case: SqliteUnkeyedSampleTestCase, tmp_path: Path
) -> None:
    adapter: RecordingCursorSqliteAdapter = RecordingCursorSqliteAdapter()
    connection: Any = adapter.connect({"path": str(tmp_path / "shop.sqlite")})
    try:
        adapter.create_table_as(
            connection=connection,
            destination="orders",
            sql=f"SELECT order_id FROM ({test_case.left_sql}) ORDER BY order_id",
            statement_recorder=recorder(),
        )
        adapter.create_table_as(
            connection=connection,
            destination="orders_next",
            sql="SELECT order_id FROM orders WHERE 0 = 1",
            statement_recorder=recorder(),
        )
        adapter.executed.clear()

        rows: tuple[tuple[tuple[str, object], ...], ...] = adapter.sample_unkeyed_side_only_rows(
            connection=connection,
            left="orders",
            right="orders_next",
            side=DIFF_LEFT_SIDE,
            limit=test_case.limit,
        )

        sample_sql, sample_cursor = adapter.executed[-1]
        assert len(rows) == test_case.expected_row_count, test_case.description
        assert {dict(row)["order_id"] for row in rows} <= test_case.expected_order_ids, (
            test_case.description
        )
        assert sample_sql.endswith(f"LIMIT {test_case.limit}"), test_case.description
        with pytest.raises(sqlite3.ProgrammingError):
            sample_cursor.fetchall()
    finally:
        adapter.close(connection)


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
