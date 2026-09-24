"""Unit tests for cursor intrinsics rendered in SQL-test model expansion."""

from __future__ import annotations

import pytest

from sqlbuild.compiler.planner._helpers.sql_tests.cursor_window import (
    render_test_cursor_intrinsics,
)
from tests.unit.src.sqlbuild.compiler.planner._helpers.sql_test_assembly._test_types import (
    CursorWindowRenderingTestCase,
)
from tests.unit.src.sqlbuild.compiler.planner._helpers.sql_test_assembly.helpers import (
    CURSOR_WINDOW_ADAPTERS,
    CURSOR_WINDOW_MODEL_SQL,
    build_cursor_model,
    build_windowed_sql_test,
)


@pytest.mark.parametrize(
    "test_case",
    (
        CursorWindowRenderingTestCase(
            description="duckdb timestamp default window",
            adapter_name="duckdb",
            cursor_type="timestamp",
            cursor_grain="day",
            cursor_start=None,
            cursor_end=None,
            expected_sql=(
                "SELECT order_date FROM orders WHERE order_date >= "
                "TIMESTAMP '1900-01-01 00:00:00' AND order_date < TIMESTAMP '2999-12-31 00:00:00'"
            ),
        ),
        CursorWindowRenderingTestCase(
            description="snowflake timestamp default window uses its typed literal",
            adapter_name="snowflake",
            cursor_type="timestamp",
            cursor_grain="day",
            cursor_start=None,
            cursor_end=None,
            expected_sql=(
                "SELECT order_date FROM orders WHERE order_date >= "
                "'1900-01-01 00:00:00' AND order_date < '2999-12-31 00:00:00'"
            ),
        ),
        CursorWindowRenderingTestCase(
            description="integer default window",
            adapter_name="snowflake",
            cursor_type="integer",
            cursor_grain=None,
            cursor_start=None,
            cursor_end=None,
            expected_sql=(
                "SELECT order_date FROM orders WHERE order_date >= -1000000000000000 "
                "AND order_date < 1000000000000000"
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_model_using_cursor_intrinsics_when_rendering_default_window_then_bounds_are_typed(
    test_case: CursorWindowRenderingTestCase,
) -> None:
    rendered: str = render_test_cursor_intrinsics(
        sql=CURSOR_WINDOW_MODEL_SQL,
        model=build_cursor_model(
            cursor_type=test_case.cursor_type, cursor_grain=test_case.cursor_grain
        ),
        adapter=CURSOR_WINDOW_ADAPTERS[test_case.adapter_name],
        test=None,
    )

    assert rendered == test_case.expected_sql


@pytest.mark.parametrize(
    "test_case",
    (
        CursorWindowRenderingTestCase(
            description="declared start keeps the default end",
            adapter_name="duckdb",
            cursor_type="timestamp",
            cursor_grain="day",
            cursor_start="2026-02-01",
            cursor_end=None,
            expected_sql=(
                "SELECT order_date FROM orders WHERE order_date >= TIMESTAMP '2026-02-01' "
                "AND order_date < TIMESTAMP '2999-12-31 00:00:00'"
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_declared_test_window_when_rendering_then_declared_bounds_replace_defaults(
    test_case: CursorWindowRenderingTestCase,
) -> None:
    rendered: str = render_test_cursor_intrinsics(
        sql=CURSOR_WINDOW_MODEL_SQL,
        model=build_cursor_model(
            cursor_type=test_case.cursor_type, cursor_grain=test_case.cursor_grain
        ),
        adapter=CURSOR_WINDOW_ADAPTERS[test_case.adapter_name],
        test=build_windowed_sql_test(
            cursor_start=test_case.cursor_start, cursor_end=test_case.cursor_end
        ),
    )

    assert rendered == test_case.expected_sql
