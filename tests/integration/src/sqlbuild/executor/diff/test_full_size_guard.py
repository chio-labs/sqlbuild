"""Integration coverage for the metadata size guard on default full model diffs."""

from __future__ import annotations

from typing import Any

import duckdb
import pytest

from sqlbuild.executor.diff.exceptions import FullDiffSizeGuardError
from sqlbuild.executor.diff.main.execute import execute_diff
from sqlbuild.executor.diff.models import (
    DiffExecutionResult,
    FullDiffModelSize,
)
from tests.integration.src.sqlbuild.executor.diff._test_types import (
    FullDiffSizeGuardBlockTestCase,
    FullDiffSizeGuardPassTestCase,
)
from tests.integration.src.sqlbuild.executor.diff.helpers import (
    RecordingDuckDbAdapter,
    guarded_full_options,
    orders_project,
    prod_dev_orders_connection,
)


@pytest.mark.parametrize(
    "test_case",
    [
        FullDiffSizeGuardPassTestCase(
            description="both sides within limits",
            left_max_rows=6,
            right_max_rows=100,
            expected_metadata_lookups=2,
        ),
        FullDiffSizeGuardPassTestCase(
            description="unlimited side skips its lookup",
            left_max_rows=None,
            right_max_rows=8,
            expected_metadata_lookups=1,
        ),
        FullDiffSizeGuardPassTestCase(
            description="both sides unlimited skip every lookup",
            left_max_rows=None,
            right_max_rows=None,
            expected_metadata_lookups=0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_tables_within_limits_when_running_default_full_diff_then_compares_rows(
    test_case: FullDiffSizeGuardPassTestCase,
) -> None:
    adapter: RecordingDuckDbAdapter = RecordingDuckDbAdapter()
    connection: duckdb.DuckDBPyConnection = prod_dev_orders_connection(right_relation_kind="TABLE")
    try:
        result: DiffExecutionResult = execute_diff(
            adapter=adapter,
            connection=connection,
            left_project=orders_project("prod"),
            right_project=orders_project("dev"),
            selected_names=("orders",),
            options=guarded_full_options(
                left_max_rows=test_case.left_max_rows,
                right_max_rows=test_case.right_max_rows,
            ),
        )
    finally:
        connection.close()

    row_result: Any = result.model_results[0].row_result
    assert row_result is not None
    assert row_result.left_count == 6
    assert row_result.right_count == 8
    lookups: int = sum("duckdb_tables()" in sql for sql in adapter.statements)
    assert lookups == test_case.expected_metadata_lookups


@pytest.mark.parametrize(
    "test_case",
    [
        FullDiffSizeGuardBlockTestCase(
            description="right side over its limit",
            left_max_rows=100,
            right_max_rows=7,
            right_relation_kind="TABLE",
            expected_left_row_count=6,
            expected_right_row_count=8,
            expected_left_exceeds=False,
            expected_right_exceeds=True,
        ),
        FullDiffSizeGuardBlockTestCase(
            description="left side over its limit",
            left_max_rows=5,
            right_max_rows=100,
            right_relation_kind="TABLE",
            expected_left_row_count=6,
            expected_right_row_count=8,
            expected_left_exceeds=True,
            expected_right_exceeds=False,
        ),
        FullDiffSizeGuardBlockTestCase(
            description="view with unknown size counts as over",
            left_max_rows=100,
            right_max_rows=100,
            right_relation_kind="VIEW",
            expected_left_row_count=6,
            expected_right_row_count=None,
            expected_left_exceeds=False,
            expected_right_exceeds=True,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_table_over_limit_when_running_default_full_diff_then_stops_before_reading_data(
    test_case: FullDiffSizeGuardBlockTestCase,
) -> None:
    adapter: RecordingDuckDbAdapter = RecordingDuckDbAdapter()
    connection: duckdb.DuckDBPyConnection = prod_dev_orders_connection(
        right_relation_kind=test_case.right_relation_kind
    )
    try:
        with pytest.raises(FullDiffSizeGuardError) as error_info:
            execute_diff(
                adapter=adapter,
                connection=connection,
                left_project=orders_project("prod"),
                right_project=orders_project("dev"),
                selected_names=("orders",),
                options=guarded_full_options(
                    left_max_rows=test_case.left_max_rows,
                    right_max_rows=test_case.right_max_rows,
                ),
            )
    finally:
        connection.close()

    blocked: tuple[FullDiffModelSize, ...] = error_info.value.blocked
    assert [model.name for model in blocked] == ["orders"]
    assert blocked[0].left.row_count == test_case.expected_left_row_count
    assert blocked[0].right.row_count == test_case.expected_right_row_count
    assert blocked[0].left.exceeds_limit is test_case.expected_left_exceeds
    assert blocked[0].right.exceeds_limit is test_case.expected_right_exceeds
    assert blocked[0].has_cursor is False
    assert adapter.statements
    assert all("duckdb_tables()" in sql for sql in adapter.statements)


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
