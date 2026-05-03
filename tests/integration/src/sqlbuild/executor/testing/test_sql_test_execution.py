"""Integration tests for SQL unit test execution."""

from __future__ import annotations

from typing import Any

import pytest

from sqlbuild.executor.testing.models import SqlTestExecutionResult
from sqlbuild.executor.testing.types import SqlTestOutcome
from sqlbuild.integrations.duckdb.client import DuckDbAdapter
from tests.integration.src.sqlbuild.executor.testing._test_types import (
    SqlTestExecutionTestCase,
)
from tests.integration.src.sqlbuild.executor.testing.helpers import (
    run_sql_test,
    verify_test_result,
)


class TinySqlLimitDuckDbAdapter(DuckDbAdapter):
    def recommended_max_sql_length(self) -> int | None:
        return 80


SUCCESS_TEST_CASES: list[SqlTestExecutionTestCase] = [
    SqlTestExecutionTestCase(
        description="single step passes when actual matches expected",
        chain_steps=(
            (
                "stg_orders",
                "SELECT 1 AS id, 'alice' AS name",
                "SELECT 1 AS id, 'alice' AS name",
            ),
        ),
        expected_outcome=SqlTestOutcome.PASS,
        expected_step_count=1,
    ),
    SqlTestExecutionTestCase(
        description="multi-step chain passes when all steps match",
        chain_steps=(
            (
                "stg_orders",
                "SELECT 1 AS id, 'alice' AS name",
                "SELECT 1 AS id, 'alice' AS name",
            ),
            (
                "dim_customers",
                "SELECT 1 AS id, 'alice' AS name UNION ALL SELECT 2 AS id, 'bob' AS name",
                "SELECT 1 AS id, 'alice' AS name UNION ALL SELECT 2 AS id, 'bob' AS name",
            ),
        ),
        expected_outcome=SqlTestOutcome.PASS,
        expected_step_count=2,
    ),
    SqlTestExecutionTestCase(
        description="multiple rows pass when all match",
        chain_steps=(
            (
                "fact_events",
                "SELECT 1 AS id UNION ALL SELECT 2 AS id UNION ALL SELECT 3 AS id",
                "SELECT 1 AS id UNION ALL SELECT 2 AS id UNION ALL SELECT 3 AS id",
            ),
        ),
        expected_outcome=SqlTestOutcome.PASS,
        expected_step_count=1,
    ),
    SqlTestExecutionTestCase(
        description="empty results pass when both return zero rows",
        chain_steps=(
            (
                "stg_orders",
                "SELECT 1 AS id WHERE FALSE",
                "SELECT 1 AS id WHERE FALSE",
            ),
        ),
        expected_outcome=SqlTestOutcome.PASS,
        expected_step_count=1,
    ),
]

FAILURE_TEST_CASES: list[SqlTestExecutionTestCase] = [
    SqlTestExecutionTestCase(
        description="single step fails when rows differ",
        chain_steps=(
            (
                "stg_orders",
                "SELECT 1 AS id, 'alice' AS name",
                "SELECT 1 AS id, 'bob' AS name",
            ),
        ),
        expected_outcome=SqlTestOutcome.FAIL,
        expected_step_count=1,
        expected_failed_models=("stg_orders",),
        expected_error_fragment="stg_orders",
    ),
    SqlTestExecutionTestCase(
        description="fails when actual has extra rows",
        chain_steps=(
            (
                "stg_orders",
                "SELECT 1 AS id UNION ALL SELECT 2 AS id",
                "SELECT 1 AS id",
            ),
        ),
        expected_outcome=SqlTestOutcome.FAIL,
        expected_step_count=1,
        expected_failed_models=("stg_orders",),
    ),
    SqlTestExecutionTestCase(
        description="fails when actual is missing rows",
        chain_steps=(
            (
                "stg_orders",
                "SELECT 1 AS id",
                "SELECT 1 AS id UNION ALL SELECT 2 AS id",
            ),
        ),
        expected_outcome=SqlTestOutcome.FAIL,
        expected_step_count=1,
        expected_failed_models=("stg_orders",),
    ),
    SqlTestExecutionTestCase(
        description="multi-step chain with second step failing",
        chain_steps=(
            (
                "stg_orders",
                "SELECT 1 AS id, 'alice' AS name",
                "SELECT 1 AS id, 'alice' AS name",
            ),
            (
                "dim_customers",
                "SELECT 1 AS id, 'wrong' AS name",
                "SELECT 1 AS id, 'right' AS name",
            ),
        ),
        expected_outcome=SqlTestOutcome.FAIL,
        expected_step_count=2,
        expected_failed_models=("dim_customers",),
        expected_error_fragment="dim_customers",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    SUCCESS_TEST_CASES,
    ids=[case.description for case in SUCCESS_TEST_CASES],
)
def test_given_matching_sql_when_executing_test_then_passes(
    test_case: SqlTestExecutionTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    result: SqlTestExecutionResult = run_sql_test(
        test_case=test_case, adapter=adapter, connection=connection
    )

    assert result.outcome == test_case.expected_outcome
    verify_test_result(result=result, test_case=test_case)


@pytest.mark.parametrize(
    "test_case",
    FAILURE_TEST_CASES,
    ids=[case.description for case in FAILURE_TEST_CASES],
)
def test_given_mismatching_sql_when_executing_test_then_fails(
    test_case: SqlTestExecutionTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    result: SqlTestExecutionResult = run_sql_test(
        test_case=test_case, adapter=adapter, connection=connection
    )

    assert result.outcome == test_case.expected_outcome
    verify_test_result(result=result, test_case=test_case)


@pytest.mark.parametrize(
    "test_case",
    [
        SqlTestExecutionTestCase(
            description="error on invalid SQL stops chain early",
            chain_steps=(
                (
                    "bad_model",
                    "SELECT * FROM nonexistent_table_xyz",
                    "SELECT 1 AS id",
                ),
                (
                    "never_reached",
                    "SELECT 1 AS id",
                    "SELECT 1 AS id",
                ),
            ),
            expected_outcome=SqlTestOutcome.ERROR,
            expected_step_count=1,
            expected_error_fragment="bad_model",
        ),
    ],
    ids=["error on invalid SQL stops chain early"],
)
def test_given_invalid_sql_when_executing_test_then_errors(
    test_case: SqlTestExecutionTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    result: SqlTestExecutionResult = run_sql_test(
        test_case=test_case, adapter=adapter, connection=connection
    )

    assert result.outcome == test_case.expected_outcome
    verify_test_result(result=result, test_case=test_case)


@pytest.mark.parametrize(
    "test_case",
    [
        SqlTestExecutionTestCase(
            description="oversized combined unit test sql fails with clear guidance",
            chain_steps=(
                (
                    "wide_model",
                    "SELECT 1 AS col_1, 2 AS col_2, 3 AS col_3, 4 AS col_4, 5 AS col_5",
                    "SELECT 1 AS col_1, 2 AS col_2, 3 AS col_3, 4 AS col_4, 5 AS col_5",
                ),
            ),
            expected_outcome=SqlTestOutcome.ERROR,
            expected_step_count=1,
            expected_error_fragment="wide_model",
        ),
    ],
    ids=["oversized combined unit test sql fails with clear guidance"],
)
def test_given_oversized_unit_test_sql_when_executing_then_it_returns_clear_error(
    test_case: SqlTestExecutionTestCase,
    connection: Any,
) -> None:
    result: SqlTestExecutionResult = run_sql_test(
        test_case=test_case,
        adapter=TinySqlLimitDuckDbAdapter(),
        connection=connection,
    )

    assert result.outcome == test_case.expected_outcome
    assert result.error_message is not None
    assert "recommended maximum" in result.error_message
    assert "scenario test" in result.error_message
    verify_test_result(result=result, test_case=test_case)
