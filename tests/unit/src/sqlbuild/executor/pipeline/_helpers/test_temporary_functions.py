"""Tests for rewriting test SQL onto temporary function copies."""

from __future__ import annotations

import pytest

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.executor.pipeline._helpers.temporary_functions import rewrite_function_calls
from tests.unit.src.sqlbuild.executor.pipeline._helpers._test_types import (
    FunctionCallRewriteTestCase,
)

_REPLACEMENTS: dict[str, str] = {
    "analytics.is_completed_order": 'temp.main."is_completed_order"',
    '"warehouse"."analytics"."customer_orders"': 'temp.main."customer_orders"',
}


@pytest.mark.parametrize(
    "test_case",
    [
        FunctionCallRewriteTestCase(
            description="scalar call moves to the temporary copy",
            sql="SELECT analytics.is_completed_order(status) FROM orders",
            expected_sql='SELECT temp.main."is_completed_order"(status) FROM orders',
        ),
        FunctionCallRewriteTestCase(
            description="whitespace before the argument list still matches",
            sql="SELECT analytics.is_completed_order (status)",
            expected_sql='SELECT temp.main."is_completed_order" (status)',
        ),
        FunctionCallRewriteTestCase(
            description="quoted table function target moves to the temporary copy",
            sql='SELECT * FROM "warehouse"."analytics"."customer_orders"(7)',
            expected_sql='SELECT * FROM temp.main."customer_orders"(7)',
        ),
        FunctionCallRewriteTestCase(
            description="longer names and non-call mentions stay unchanged",
            sql=(
                "SELECT staging.analytics.is_completed_order(status), "
                "analytics.is_completed_order_v2(status), "
                "'analytics.is_completed_order' AS label"
            ),
            expected_sql=(
                "SELECT staging.analytics.is_completed_order(status), "
                "analytics.is_completed_order_v2(status), "
                "'analytics.is_completed_order' AS label"
            ),
        ),
        FunctionCallRewriteTestCase(
            description="calls inside string literals and comments stay unchanged",
            sql=(
                "SELECT analytics.is_completed_order(status), "
                "'analytics.is_completed_order(x)' AS label -- analytics.is_completed_order(y)\n"
                "/* analytics.is_completed_order(z) */ FROM orders"
            ),
            expected_sql=(
                'SELECT temp.main."is_completed_order"(status), '
                "'analytics.is_completed_order(x)' AS label -- analytics.is_completed_order(y)\n"
                "/* analytics.is_completed_order(z) */ FROM orders"
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_deployed_function_calls_when_rewriting_then_only_calls_move_to_temporary_copies(
    test_case: FunctionCallRewriteTestCase,
) -> None:
    rewritten: str = rewrite_function_calls(
        sql=test_case.sql,
        replacements=_REPLACEMENTS,
        syntax=DuckDbAdapter.sql_lexical_syntax.native_mapping,
    )

    assert rewritten == test_case.expected_sql, test_case.description
