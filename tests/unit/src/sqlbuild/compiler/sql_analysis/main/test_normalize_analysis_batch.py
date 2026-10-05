from __future__ import annotations

import pytest

from sqlbuild.compiler.sql_analysis.main._normalize_analysis import normalize_analysis_sql
from sqlbuild.compiler.sql_analysis.main._normalize_analysis_batch import (
    normalize_analysis_sql_results,
)
from tests.unit.src.sqlbuild.compiler.sql_analysis.main._test_types import (
    NormalizationBatchFailureTestCase,
    NormalizationBatchTestCase,
)
from tests.unit.src.sqlbuild.compiler.sql_analysis.main.helpers import (
    pool_catalog,
    without_catalog,
)


@pytest.mark.parametrize(
    "test_case",
    (
        NormalizationBatchTestCase(
            description="stubbed relations and placeholders in turn",
            dialect="snowflake",
            requests=(
                (
                    'SELECT * FROM __ref("orders") JOIN __ref("customers") USING (customer_id)',
                    {"orders": "__sqb_rel_0", "customers": "__sqb_rel_1"},
                    {},
                ),
                ("SELECT payload:item[0] AS item FROM inventory", {}, {}),
                ("SELECT 1 AS quantity LIMIT @@@limit", {}, {"limit": "10"}),
            ),
            catalog=without_catalog,
            expected_stubbed_sql="SELECT * FROM __sqb_rel_0 JOIN __sqb_rel_1 USING (customer_id)",
        ),
        NormalizationBatchTestCase(
            description="stubbed relations and placeholders on the catalog pool",
            dialect="snowflake",
            requests=(
                (
                    'SELECT * FROM __ref("orders") JOIN __ref("customers") USING (customer_id)',
                    {"orders": "__sqb_rel_0", "customers": "__sqb_rel_1"},
                    {},
                ),
                ("SELECT payload:item[0] AS item FROM inventory", {}, {}),
                ("SELECT 1 AS quantity LIMIT @@@limit", {}, {"limit": "10"}),
            ),
            catalog=pool_catalog,
            expected_stubbed_sql="SELECT * FROM __sqb_rel_0 JOIN __sqb_rel_1 USING (customer_id)",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_batch_when_normalizing_then_matches_single_normalizations_in_order(
    test_case: NormalizationBatchTestCase,
) -> None:
    expected: list[str | Exception] = [
        normalize_analysis_sql(
            sql=sql, dialect=test_case.dialect, stubs=stubs, placeholders=placeholders
        )
        for sql, stubs, placeholders in test_case.requests
    ]

    results: list[str | Exception] = normalize_analysis_sql_results(
        dialect=test_case.dialect,
        requests=test_case.requests,
        catalog=test_case.catalog(test_case.dialect),
    )

    assert results == expected
    assert results[0] == test_case.expected_stubbed_sql


@pytest.mark.parametrize(
    "test_case",
    (
        NormalizationBatchFailureTestCase(
            description="unterminated quote in turn",
            dialect="snowflake",
            before=("SELECT id FROM products",),
            failing="SELECT 'unterminated FROM orders",
            after=("SELECT /* unterminated FROM customers", "SELECT id FROM customers"),
            catalog=without_catalog,
            expected_error_type=ValueError,
            expected_result_types=("str", "ValueError", "ValueError", "str"),
        ),
        NormalizationBatchFailureTestCase(
            description="unterminated quote on the catalog pool",
            dialect="snowflake",
            before=("SELECT id FROM products",),
            failing="SELECT 'unterminated FROM orders",
            after=("SELECT /* unterminated FROM customers", "SELECT id FROM customers"),
            catalog=pool_catalog,
            expected_error_type=ValueError,
            expected_result_types=("str", "ValueError", "ValueError", "str"),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_failing_member_when_normalizing_batch_then_keeps_its_single_call_error_in_place(
    test_case: NormalizationBatchFailureTestCase,
) -> None:
    with pytest.raises(test_case.expected_error_type) as raised:
        _ = normalize_analysis_sql(sql=test_case.failing, dialect=test_case.dialect)

    results: list[str | Exception] = normalize_analysis_sql_results(
        dialect=test_case.dialect,
        requests=[
            (sql, None, None) for sql in (*test_case.before, test_case.failing, *test_case.after)
        ],
        catalog=test_case.catalog(test_case.dialect),
    )
    first_error: str | Exception = results[len(test_case.before)]

    assert results[: len(test_case.before)] == [
        normalize_analysis_sql(sql=sql, dialect=test_case.dialect) for sql in test_case.before
    ]
    assert type(first_error) is type(raised.value)
    assert str(first_error) == str(raised.value)
    assert tuple(type(result).__name__ for result in results) == test_case.expected_result_types


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
