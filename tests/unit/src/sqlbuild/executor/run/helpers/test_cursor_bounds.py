from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import duckdb
import pytest

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.planner.models import CursorBounds, CursorInputRelation
from sqlbuild.compiler.planner.types import CursorType
from sqlbuild.executor.run.helpers.cursor_bounds import resolve_runtime_cursor_bounds
from tests.unit.src.sqlbuild.executor.run.helpers._test_types import RuntimeCursorStartTestCase
from tests.unit.src.sqlbuild.executor.run.helpers.helpers import FakeCursorAdapter

TEST_CASES: list[RuntimeCursorStartTestCase] = [
    RuntimeCursorStartTestCase(
        description="runtime timestamp bounds clamp to configured floor",
        target_max=None,
        upstream_min=datetime(2024, 1, 1, tzinfo=UTC),
        upstream_max=datetime(2024, 2, 1, tzinfo=UTC),
        cursor_type=CursorType.TIMESTAMP,
        cursor_start="2024-01-15T00:00:00+00:00",
        expected_start="2024-01-15T00:00:00+00:00",
        expected_end="2024-02-01T00:00:01+00:00",
    ),
    RuntimeCursorStartTestCase(
        description="runtime integer bounds clamp to configured floor",
        target_max=None,
        upstream_min=50,
        upstream_max=200,
        cursor_type=CursorType.INTEGER,
        cursor_start="100",
        expected_start="100",
        expected_end="201",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    TEST_CASES,
    ids=[case.description for case in TEST_CASES],
)
def test_given_runtime_cursor_start_when_resolving_bounds_then_applies_lower_floor(
    test_case: RuntimeCursorStartTestCase,
) -> None:
    connection: duckdb.DuckDBPyConnection = duckdb.connect(":memory:")
    cursor_column_type: str = (
        "TIMESTAMPTZ" if test_case.cursor_type == CursorType.TIMESTAMP else "INTEGER"
    )
    connection.execute(f"CREATE TABLE upstream_data (cursor_value {cursor_column_type})")
    connection.execute("INSERT INTO upstream_data VALUES (?)", [test_case.upstream_min])
    connection.execute("INSERT INTO upstream_data VALUES (?)", [test_case.upstream_max])

    cursor_bounds: CursorBounds | None = resolve_runtime_cursor_bounds(
        adapter=cast(BaseAdapter, FakeCursorAdapter()),
        connection=connection,
        target_relation="target_data",
        cursor_column="cursor_value",
        cursor_type=test_case.cursor_type,
        cursor_grain=None,
        cursor_start=test_case.cursor_start,
        cursor_input_relations=(
            CursorInputRelation(
                relation="upstream_data",
                cursor_column="cursor_value",
            ),
        ),
    )

    assert cursor_bounds is not None
    assert cursor_bounds.start == test_case.expected_start
    assert cursor_bounds.end == test_case.expected_end
