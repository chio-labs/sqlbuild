from __future__ import annotations

import pytest

pytest.importorskip("polyglot_sql")

from sqlbuild.compiler.compile.helpers.sqlglot_tests import (  # noqa: E402
    extract_expected_branch_column_names_with_sqlglot,
)
from tests.unit.src.sqlbuild.compiler.compile.helpers._test_types import (  # noqa: E402
    ExtractSqlglotExpectedBranchesErrorTestCase,
    ExtractSqlglotExpectedBranchesTestCase,
)

TEST_CASES: list[ExtractSqlglotExpectedBranchesTestCase] = [
    ExtractSqlglotExpectedBranchesTestCase(
        description="extracts aliases from parenthesized union branches",
        sql="""
        SELECT CAST(1 AS INTEGER) AS order_id, CAST('paid' AS VARCHAR) AS status
        UNION ALL
        (SELECT CAST(2 AS INTEGER) AS order_id, CAST('created' AS VARCHAR) AS status)
        """.strip(),
        expected_branch_column_names=(
            ("order_id", "status"),
            ("order_id", "status"),
        ),
    ),
    ExtractSqlglotExpectedBranchesTestCase(
        description="extracts bare column names from select projections",
        sql="SELECT order_id, status FROM expected_rows",
        expected_branch_column_names=(("order_id", "status"),),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    TEST_CASES,
    ids=[case.description for case in TEST_CASES],
)
def test_given_sqlglot_available_when_extracting_expected_branches_then_it_returns_names(
    test_case: ExtractSqlglotExpectedBranchesTestCase,
) -> None:
    branch_column_names: tuple[tuple[str, ...], ...] | None = (
        extract_expected_branch_column_names_with_sqlglot(
            sql=test_case.sql,
            file_label="tests/unit/orders.sql",
        )
    )

    assert branch_column_names == test_case.expected_branch_column_names


ERROR_TEST_CASES: list[ExtractSqlglotExpectedBranchesErrorTestCase] = [
    ExtractSqlglotExpectedBranchesErrorTestCase(
        description="raises when a non trivial projection lacks an alias",
        sql="SELECT CAST(1 AS INTEGER), CAST('paid' AS VARCHAR) AS status",
        expected_error_fragment="must alias every non-trivial __expected__<model> projection",
    ),
    ExtractSqlglotExpectedBranchesErrorTestCase(
        description="raises when expected branch is not a select query",
        sql="SELECT 1 AS order_id UNION ALL VALUES (2)",
        expected_error_fragment="set-operation branch as a SELECT query",
    ),
    ExtractSqlglotExpectedBranchesErrorTestCase(
        description="raises when expected select uses star projection",
        sql="SELECT * FROM expected_rows",
        expected_error_fragment=r"must not use SELECT \* in __expected__<model> CTEs",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    ERROR_TEST_CASES,
    ids=[case.description for case in ERROR_TEST_CASES],
)
def test_given_invalid_sqlglot_expected_branches_when_extracting_then_it_raises_clear_errors(
    test_case: ExtractSqlglotExpectedBranchesErrorTestCase,
) -> None:
    with pytest.raises(ValueError, match=test_case.expected_error_fragment):
        extract_expected_branch_column_names_with_sqlglot(
            sql=test_case.sql,
            file_label="tests/unit/orders.sql",
        )
