from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import duckdb
import pytest

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.planner.models import CursorBounds, CursorInputRelation
from sqlbuild.compiler.planner.types import CursorType
from sqlbuild.executor.run.helpers.validation.cursor_bounds import resolve_runtime_cursor_bounds
from tests.unit.src.sqlbuild.executor.run.helpers._test_types import (
    RuntimeCursorStartTestCase,
    RuntimeTargetMaxTestCase,
    RuntimeTargetProbeFailureTestCase,
)
from tests.unit.src.sqlbuild.executor.run.helpers.helpers import FakeCursorAdapter


@pytest.mark.parametrize(
    "test_case",
    [
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
    ],
    ids=lambda case: case.description,
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
        target_database=None,
        target_schema=None,
        target_name="target_data",
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


@pytest.mark.parametrize(
    "test_case",
    [
        RuntimeTargetMaxTestCase(
            description="existing target relation seeds start from target max",
            target_rows=(80, 100),
            upstream_min=50,
            upstream_max=200,
            cursor_type=CursorType.INTEGER,
            expected_start="100",
            expected_end="201",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_existing_target_relation_when_resolving_bounds_then_starts_from_target_max(
    test_case: RuntimeTargetMaxTestCase,
) -> None:
    connection: duckdb.DuckDBPyConnection = duckdb.connect(":memory:")
    connection.execute("CREATE TABLE upstream_data (cursor_value INTEGER)")
    connection.execute("INSERT INTO upstream_data VALUES (?)", [test_case.upstream_min])
    connection.execute("INSERT INTO upstream_data VALUES (?)", [test_case.upstream_max])
    connection.execute("CREATE TABLE target_data (cursor_value INTEGER)")
    target_row: object
    for target_row in test_case.target_rows:
        connection.execute("INSERT INTO target_data VALUES (?)", [target_row])

    cursor_bounds: CursorBounds | None = resolve_runtime_cursor_bounds(
        adapter=cast(BaseAdapter, FakeCursorAdapter(target_relation_exists=True)),
        connection=connection,
        target_relation="target_data",
        target_database=None,
        target_schema=None,
        target_name="target_data",
        cursor_column="cursor_value",
        cursor_type=test_case.cursor_type,
        cursor_grain=None,
        cursor_start=None,
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


@pytest.mark.parametrize(
    "test_case",
    [
        RuntimeTargetProbeFailureTestCase(
            description="target max query failure propagates instead of widening the window",
            expected_error_type=duckdb.CatalogException,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_target_max_query_failure_when_resolving_bounds_then_propagates_error(
    test_case: RuntimeTargetProbeFailureTestCase,
) -> None:
    connection: duckdb.DuckDBPyConnection = duckdb.connect(":memory:")
    connection.execute("CREATE TABLE upstream_data (cursor_value INTEGER)")
    connection.execute("INSERT INTO upstream_data VALUES (50)")
    connection.execute("INSERT INTO upstream_data VALUES (200)")

    with pytest.raises(test_case.expected_error_type):
        resolve_runtime_cursor_bounds(
            adapter=cast(BaseAdapter, FakeCursorAdapter(target_relation_exists=True)),
            connection=connection,
            target_relation="target_data",
            target_database=None,
            target_schema=None,
            target_name="target_data",
            cursor_column="cursor_value",
            cursor_type=CursorType.INTEGER,
            cursor_grain=None,
            cursor_start=None,
            cursor_input_relations=(
                CursorInputRelation(
                    relation="upstream_data",
                    cursor_column="cursor_value",
                ),
            ),
        )
