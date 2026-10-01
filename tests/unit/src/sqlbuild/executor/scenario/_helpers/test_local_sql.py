from __future__ import annotations

import pytest

from sqlbuild.executor.scenario._helpers.local.sql import transpile_sql_for_local_duckdb
from tests.unit.src.sqlbuild.executor.scenario._helpers._test_types import (
    LocalScenarioSqlTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        LocalScenarioSqlTestCase(
            description="DuckDB captures run their authored SQL without regeneration",
            source_dialect="duckdb",
            sql="select ifnull(total, 0) as total, list_value(1, 2) as ids from orders",
            expected_sql="select ifnull(total, 0) as total, list_value(1, 2) as ids from orders",
        ),
        LocalScenarioSqlTestCase(
            description="other captured dialects are translated for local DuckDB",
            source_dialect="snowflake",
            sql="select IFNULL(total, 0) as total from orders",
            expected_sql="SELECT COALESCE(total, 0) AS total FROM orders",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_captured_dialect_when_preparing_local_scenario_sql_then_only_translates_foreign_sql(
    test_case: LocalScenarioSqlTestCase,
) -> None:
    result: str = transpile_sql_for_local_duckdb(
        sql=test_case.sql,
        source_dialect=test_case.source_dialect,
        scenario_name="order_totals",
        resource_kind="model",
        resource_name="order_totals",
    )

    assert result == test_case.expected_sql


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
