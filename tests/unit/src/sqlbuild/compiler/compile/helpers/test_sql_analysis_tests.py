from __future__ import annotations

import pytest

pytest.importorskip("polyglot_sql")

from sqlbuild.compiler.compile.helpers.analysis.tests import (  # noqa: E402
    extract_expected_branch_column_names_with_sql_analysis,
)
from tests.unit.src.sqlbuild.compiler.compile.helpers._test_types import (  # noqa: E402
    ExtractSqlAnalysisExpectedBranchesErrorTestCase,
    ExtractSqlAnalysisExpectedBranchesTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ExtractSqlAnalysisExpectedBranchesTestCase(
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
        ExtractSqlAnalysisExpectedBranchesTestCase(
            description="extracts bare column names from select projections",
            sql="SELECT order_id, status FROM expected_rows",
            expected_branch_column_names=(("order_id", "status"),),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_sql_analysis_available_when_extracting_expected_branches_then_it_returns_names(
    test_case: ExtractSqlAnalysisExpectedBranchesTestCase,
) -> None:
    branch_column_names: tuple[tuple[str, ...], ...] | None = (
        extract_expected_branch_column_names_with_sql_analysis(
            sql=test_case.sql,
            file_label="tests/unit/orders.sql",
        )
    )

    assert branch_column_names == test_case.expected_branch_column_names


@pytest.mark.parametrize(
    "test_case",
    [
        ExtractSqlAnalysisExpectedBranchesErrorTestCase(
            description="raises when a non trivial projection lacks an alias",
            sql="SELECT CAST(1 AS INTEGER), CAST('paid' AS VARCHAR) AS status",
            expected_error_fragment="must alias every non-trivial __expected__<model> projection",
        ),
        ExtractSqlAnalysisExpectedBranchesErrorTestCase(
            description="raises when expected branch is not a select query",
            sql="SELECT 1 AS order_id UNION ALL VALUES (2)",
            expected_error_fragment="set-operation branch as a SELECT query",
        ),
        ExtractSqlAnalysisExpectedBranchesErrorTestCase(
            description="raises when expected select uses star projection",
            sql="SELECT * FROM expected_rows",
            expected_error_fragment=r"must not use SELECT \* in __expected__<model> CTEs",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_sql_analysis_expected_branches_when_extracting_then_it_raises_clear_errors(
    test_case: ExtractSqlAnalysisExpectedBranchesErrorTestCase,
) -> None:
    with pytest.raises(ValueError, match=test_case.expected_error_fragment):
        extract_expected_branch_column_names_with_sql_analysis(
            sql=test_case.sql,
            file_label="tests/unit/orders.sql",
        )
