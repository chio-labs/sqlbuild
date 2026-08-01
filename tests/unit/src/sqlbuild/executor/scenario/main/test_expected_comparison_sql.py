from __future__ import annotations

import pytest

from sqlbuild.executor.scenario.main.expected_comparison_sql import (
    build_scenario_expected_comparison_sql,
)
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
        )
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
    )

    for expected_fragment in test_case.expected_fragments:
        assert expected_fragment in sql
