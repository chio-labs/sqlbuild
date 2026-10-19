from __future__ import annotations

import pytest

from sqlbuild._native import build_scenario_expected_comparison_sql
from tests.unit.src.sqlbuild.executor.scenario.main._test_types import (
    ScenarioExpectedComparisonSqlTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ScenarioExpectedComparisonSqlTestCase(
            description="aliases the scenario set difference derived table",
            set_difference_operator="EXCEPT",
            expected_fragments=(
                "SELECT * FROM __actual EXCEPT SELECT * FROM __expected",
                ") AS __sqlbuild_mismatch",
            ),
        ),
        ScenarioExpectedComparisonSqlTestCase(
            description="compares listed columns by name in both directions",
            set_difference_operator="EXCEPT",
            compared_columns=("status", "order_id"),
            expected_fragments=(
                "SELECT status, order_id FROM __actual EXCEPT SELECT status, order_id FROM "
                "__expected) AS __sqlbuild_mismatch) AS unexpected_count",
                "SELECT status, order_id FROM __expected EXCEPT SELECT status, order_id FROM "
                "__actual) AS __sqlbuild_missing) AS missing_count",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_expected_output_when_building_comparison_then_aliases_set_difference(
    test_case: ScenarioExpectedComparisonSqlTestCase,
) -> None:
    sql: str = build_scenario_expected_comparison_sql(
        actual_sql="SELECT 1 AS order_id",
        expected_sql="SELECT 1 AS order_id",
        set_difference_operator=test_case.set_difference_operator,
        compared_columns=test_case.compared_columns,
    )

    for expected_fragment in test_case.expected_fragments:
        assert expected_fragment in sql
