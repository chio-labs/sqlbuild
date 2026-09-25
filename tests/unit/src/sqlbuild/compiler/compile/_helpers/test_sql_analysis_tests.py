from __future__ import annotations

import pytest

pytest.importorskip("polyglot_sql")

from sqlbuild.compiler.compile._helpers.analysis.tests import (  # noqa: E402
    extract_expected_branch_column_names_with_sql_analysis,
)
from tests.unit.src.sqlbuild.compiler.compile._helpers._test_types import (  # noqa: E402
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
        ExtractSqlAnalysisExpectedBranchesTestCase(
            description="fallback ignores an apostrophe in a line comment",
            sql="SELECT 1 AS order_id; -- don't mix\nUNION ALL SELECT 2 AS order_id",
            expected_branch_column_names=(("order_id",), ("order_id",)),
        ),
        ExtractSqlAnalysisExpectedBranchesTestCase(
            description="fallback ignores a set operation inside a block comment",
            sql="SELECT 1 AS order_id; /* UNION ALL */ UNION ALL SELECT 2 AS order_id",
            expected_branch_column_names=(("order_id",), ("order_id",)),
        ),
        ExtractSqlAnalysisExpectedBranchesTestCase(
            description="fallback splits union distinct",
            sql="SELECT 1 AS order_id; UNION DISTINCT SELECT 2 AS order_id",
            expected_branch_column_names=(("order_id",), ("order_id",)),
        ),
        ExtractSqlAnalysisExpectedBranchesTestCase(
            description="fallback keeps doubled quotes inside one string",
            sql="SELECT 1 AS order_id; UNION SELECT 'it''s UNION' AS order_id",
            expected_branch_column_names=(("order_id",), ("order_id",)),
        ),
        ExtractSqlAnalysisExpectedBranchesTestCase(
            description="parsed intersect and except return every branch in order",
            sql=(
                "SELECT 1 AS order_id UNION SELECT 2 AS order_id EXCEPT ALL "
                "SELECT 3 AS other_id INTERSECT DISTINCT SELECT 4 AS extra_id"
            ),
            expected_branch_column_names=(
                ("order_id",),
                ("order_id",),
                ("other_id",),
                ("extra_id",),
            ),
        ),
        ExtractSqlAnalysisExpectedBranchesTestCase(
            description="fallback splits intersect and except with quantifiers",
            sql=(
                "SELECT 1 AS order_id; INTERSECT ALL SELECT 2 AS order_id "
                "EXCEPT DISTINCT SELECT 3 AS other_id"
            ),
            expected_branch_column_names=(("order_id",), ("order_id",), ("other_id",)),
        ),
        ExtractSqlAnalysisExpectedBranchesTestCase(
            description="fallback defers to textual analysis when a branch cannot parse",
            sql='SELECT __udf("net_amount")(1) AS amount UNION ALL SELECT 2 AS amount',
            expected_branch_column_names=None,
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
            description="fallback rejects a values branch after except",
            sql="SELECT 1 AS order_id; EXCEPT VALUES (2)",
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
