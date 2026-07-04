"""Tests for node result SQL helpers."""

from __future__ import annotations

import pytest

from sqlbuild.executor.node_results.helpers.sql import build_read_history_sql
from tests.unit.src.sqlbuild.executor.node_results.helpers._test_types import (
    NodeResultSqlTestCase,
)
from tests.unit.src.sqlbuild.executor.node_results.helpers.helpers import (
    render_test_qualified_name,
)


@pytest.mark.parametrize(
    "test_case",
    [
        NodeResultSqlTestCase(
            description="builds scoped read SQL with deterministic ordering",
            expected_fragments=(
                "FROM analytics._sqlbuild_node_results",
                "node_type = 'task'",
                "node_name = 'produce_result'",
                "target_schema = 'analytics'",
                "status IN ('success')",
                "ORDER BY ts DESC, run_id DESC",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_node_result_read_request_when_building_sql_then_scopes_and_orders_rows(
    test_case: NodeResultSqlTestCase,
) -> None:
    sql: str = build_read_history_sql(
        database=None,
        schema="analytics",
        node_type="task",
        node_name="produce_result",
        target_database=None,
        target_schema="analytics",
        target_name=None,
        statuses=("success",),
        run_id=None,
        render_qualified_name=render_test_qualified_name,
    )

    fragment: str
    for fragment in test_case.expected_fragments:
        assert fragment in sql
