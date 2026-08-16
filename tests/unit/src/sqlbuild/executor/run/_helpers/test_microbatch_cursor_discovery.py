from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import cast

import duckdb
import pytest

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.planner.models import CursorBounds, CursorInputRelation
from sqlbuild.compiler.planner.types import CursorType
from sqlbuild.errors.contracts.exceptions import ExecutorInputError
from sqlbuild.executor.run._helpers.materializations.microbatch import _discover_cursor_range
from tests.unit.src.sqlbuild.executor.run._helpers._test_types import (
    MicrobatchCursorDiscoveryFailureTestCase,
    MicrobatchCursorDiscoveryTestCase,
)
from tests.unit.src.sqlbuild.executor.run._helpers.helpers import FakeCursorAdapter


@pytest.mark.parametrize(
    "test_case",
    [
        MicrobatchCursorDiscoveryTestCase(
            description="date cursor discovery advances the end bound past the final date",
            warehouse_column_type="DATE",
            cursor_min=date(2014, 1, 1),
            cursor_max=date(2014, 12, 31),
            cursor_type=CursorType.TIMESTAMP,
            expected_start="2014-01-01",
            expected_end="2015-01-01",
        ),
        MicrobatchCursorDiscoveryTestCase(
            description="decimal cursor discovery advances the end bound past the final value",
            warehouse_column_type="DECIMAL(38,0)",
            cursor_min=Decimal(50),
            cursor_max=Decimal(200),
            cursor_type=CursorType.INTEGER,
            expected_start="50",
            expected_end="201",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_non_datetime_cursor_when_discovering_range_then_end_bound_includes_final_value(
    test_case: MicrobatchCursorDiscoveryTestCase,
) -> None:
    connection: duckdb.DuckDBPyConnection = duckdb.connect(":memory:")
    connection.execute(
        f"CREATE TABLE upstream_data (cursor_value {test_case.warehouse_column_type})"
    )
    connection.execute("INSERT INTO upstream_data VALUES (?)", [test_case.cursor_min])
    connection.execute("INSERT INTO upstream_data VALUES (?)", [test_case.cursor_max])

    cursor_bounds: CursorBounds | None = _discover_cursor_range(
        adapter=cast(BaseAdapter, FakeCursorAdapter()),
        connection=connection,
        cursor_type=test_case.cursor_type,
        cursor_start=None,
        cursor_input_relations=(
            CursorInputRelation(relation="upstream_data", cursor_column="cursor_value"),
        ),
    )

    assert cursor_bounds is not None
    assert cursor_bounds.start == test_case.expected_start
    assert cursor_bounds.end == test_case.expected_end


@pytest.mark.parametrize(
    "test_case",
    [
        MicrobatchCursorDiscoveryFailureTestCase(
            description="unsupported cursor type fails instead of dropping the final value",
            warehouse_column_type="VARCHAR",
            cursor_min="2014-01-01",
            cursor_max="2014-12-31",
            expected_error_fragment="unsupported cursor type",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_unsupported_cursor_type_when_discovering_range_then_raises(
    test_case: MicrobatchCursorDiscoveryFailureTestCase,
) -> None:
    connection: duckdb.DuckDBPyConnection = duckdb.connect(":memory:")
    connection.execute(
        f"CREATE TABLE upstream_data (cursor_value {test_case.warehouse_column_type})"
    )
    connection.execute("INSERT INTO upstream_data VALUES (?)", [test_case.cursor_min])
    connection.execute("INSERT INTO upstream_data VALUES (?)", [test_case.cursor_max])

    with pytest.raises(ExecutorInputError, match=test_case.expected_error_fragment):
        _discover_cursor_range(
            adapter=cast(BaseAdapter, FakeCursorAdapter()),
            connection=connection,
            cursor_type=CursorType.TIMESTAMP,
            cursor_start=None,
            cursor_input_relations=(
                CursorInputRelation(relation="upstream_data", cursor_column="cursor_value"),
            ),
        )
