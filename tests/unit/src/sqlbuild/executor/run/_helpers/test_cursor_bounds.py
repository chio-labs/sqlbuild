from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import cast

import duckdb
import pytest

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.planner.models import CursorBounds, CursorInputRelation
from sqlbuild.compiler.planner.types import CursorGrain, CursorType
from sqlbuild.executor.run._helpers.validation.cursor_bounds import resolve_runtime_cursor_bounds
from sqlbuild.executor.run.models import RuntimeCursorSpec
from tests.unit.src.sqlbuild.executor.run._helpers._test_types import (
    RuntimeCursorEndBoundTestCase,
    RuntimeCursorStartTestCase,
    RuntimeTargetMaxTestCase,
    RuntimeTargetProbeFailureTestCase,
)
from tests.unit.src.sqlbuild.executor.run._helpers.helpers import FakeCursorAdapter


@pytest.mark.parametrize(
    "test_case",
    [
        RuntimeCursorStartTestCase(
            description="runtime timestamp bounds clamp to configured floor",
            target_max=None,
            upstream_min=datetime(2024, 1, 1, tzinfo=UTC),
            upstream_max=datetime(2024, 2, 1, tzinfo=UTC),
            cursor_type=CursorType.TIMESTAMP,
            warehouse_column_type="TIMESTAMPTZ",
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
            warehouse_column_type="INTEGER",
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
    connection.execute(
        f"CREATE TABLE upstream_data (cursor_value {test_case.warehouse_column_type})"
    )
    connection.execute("INSERT INTO upstream_data VALUES (?)", [test_case.upstream_min])
    connection.execute("INSERT INTO upstream_data VALUES (?)", [test_case.upstream_max])

    cursor_bounds: CursorBounds | None = resolve_runtime_cursor_bounds(
        adapter=cast(BaseAdapter, FakeCursorAdapter()),
        connection=connection,
        target_relation="target_data",
        target_database=None,
        target_schema=None,
        target_name="target_data",
        spec=RuntimeCursorSpec(
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
        ),
    )

    assert cursor_bounds is not None
    assert cursor_bounds.start == test_case.expected_start
    assert cursor_bounds.end == test_case.expected_end


@pytest.mark.parametrize(
    "test_case",
    [
        RuntimeCursorEndBoundTestCase(
            description="date cursor with day grain advances the end bound past the final date",
            upstream_min=date(2014, 1, 1),
            upstream_max=date(2014, 12, 31),
            cursor_type=CursorType.TIMESTAMP,
            cursor_grain=CursorGrain.DAY,
            warehouse_column_type="DATE",
            expected_start="2014-01-01",
            expected_end="2015-01-01",
        ),
        RuntimeCursorEndBoundTestCase(
            description="date cursor without a grain advances the end bound past the final date",
            upstream_min=date(2014, 1, 1),
            upstream_max=date(2014, 12, 31),
            cursor_type=CursorType.TIMESTAMP,
            cursor_grain=None,
            warehouse_column_type="DATE",
            expected_start="2014-01-01",
            expected_end="2015-01-01",
        ),
        RuntimeCursorEndBoundTestCase(
            description="decimal integer cursor advances the end bound past the final value",
            upstream_min=Decimal(50),
            upstream_max=Decimal(200),
            cursor_type=CursorType.INTEGER,
            cursor_grain=None,
            warehouse_column_type="DECIMAL(38,0)",
            expected_start="50",
            expected_end="201",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_non_datetime_cursor_when_resolving_bounds_then_end_bound_includes_final_value(
    test_case: RuntimeCursorEndBoundTestCase,
) -> None:
    connection: duckdb.DuckDBPyConnection = duckdb.connect(":memory:")
    connection.execute(
        f"CREATE TABLE upstream_data (cursor_value {test_case.warehouse_column_type})"
    )
    connection.execute("INSERT INTO upstream_data VALUES (?)", [test_case.upstream_min])
    connection.execute("INSERT INTO upstream_data VALUES (?)", [test_case.upstream_max])

    cursor_bounds: CursorBounds | None = resolve_runtime_cursor_bounds(
        adapter=cast(BaseAdapter, FakeCursorAdapter()),
        connection=connection,
        target_relation="target_data",
        target_database=None,
        target_schema=None,
        target_name="target_data",
        spec=RuntimeCursorSpec(
            cursor_column="cursor_value",
            cursor_type=test_case.cursor_type,
            cursor_grain=test_case.cursor_grain,
            cursor_start=None,
            cursor_input_relations=(
                CursorInputRelation(
                    relation="upstream_data",
                    cursor_column="cursor_value",
                ),
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
        spec=RuntimeCursorSpec(
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
            spec=RuntimeCursorSpec(
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
            ),
        )
