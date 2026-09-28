"""Unit coverage for comparing stored view definitions with compatibility view SQL."""

from __future__ import annotations

import pytest

from sqlbuild.adapter.contract.main.same_view_definition import same_view_definition
from tests.unit.src.sqlbuild.adapter.contract.main._test_types import SameViewDefinitionTestCase

_SQL: str = 'SELECT "order_id", "revenue" AS "amount" FROM analytics.daily_revenue'


@pytest.mark.parametrize(
    "test_case",
    [
        SameViewDefinitionTestCase(
            description="duckdb re-serialized create statement",
            definition=(
                "CREATE VIEW analytics.revenue AS SELECT order_id, revenue AS amount "
                "FROM analytics.daily_revenue;"
            ),
            sql=_SQL,
            expected_match=True,
        ),
        SameViewDefinitionTestCase(
            description="snowflake create statement with copy grants",
            definition=(
                "CREATE OR REPLACE VIEW ANALYTICS.REVENUE COPY GRANTS AS "
                'SELECT "order_id", "revenue" AS "amount" FROM analytics.daily_revenue'
            ),
            sql=_SQL,
            expected_match=True,
        ),
        SameViewDefinitionTestCase(
            description="sql server bracketed alter statement",
            definition=(
                "ALTER VIEW [analytics].[revenue] AS SELECT [order_id], [revenue] AS [amount] "
                "FROM analytics.daily_revenue"
            ),
            sql=_SQL,
            expected_match=True,
        ),
        SameViewDefinitionTestCase(
            description="postgres rewritten body on several lines",
            definition=" SELECT order_id,\n    revenue AS amount\n   FROM analytics.daily_revenue;",
            sql=" SELECT order_id,\n    revenue AS amount\n   FROM analytics.daily_revenue;",
            expected_match=True,
        ),
        SameViewDefinitionTestCase(
            description="another view at the old name",
            definition=(
                "CREATE VIEW analytics.revenue AS SELECT order_id, amount_cents * 2 AS doubled "
                "FROM raw.raw_orders"
            ),
            sql=_SQL,
            expected_match=False,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_stored_definition_when_comparing_then_only_formatting_is_ignored(
    test_case: SameViewDefinitionTestCase,
) -> None:
    assert (
        same_view_definition(definition=test_case.definition, sql=test_case.sql)
        == test_case.expected_match
    )
