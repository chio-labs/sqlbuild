from __future__ import annotations

import pytest

from sqlbuild.compiler.sql_analysis.main._normalize_for_polyglot import (
    normalize_sql_for_polyglot,
)
from tests.unit.src.sqlbuild.compiler.sql_analysis.main._test_types import (
    PolyglotSqlNormalizationTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    (
        PolyglotSqlNormalizationTestCase(
            description="normalizes dynamic access after arithmetic and variable tokens",
            sql=(
                "SELECT amount / quantity - $discount, "
                "payload:labels[TO_VARCHAR(product_id)] FROM orders"
            ),
            dialect="snowflake",
            expected_sql=(
                "SELECT amount / quantity - $discount, "
                "GET(payload:labels, TO_VARCHAR(product_id)) FROM orders"
            ),
        ),
        PolyglotSqlNormalizationTestCase(
            description="rewrites a dynamic key after a Snowflake variant path",
            sql="SELECT payload:labels[TO_VARCHAR(payload:item_id)] FROM events",
            dialect="snowflake",
            expected_sql="SELECT GET(payload:labels, TO_VARCHAR(payload:item_id)) FROM events",
        ),
        PolyglotSqlNormalizationTestCase(
            description="preserves a static key after a Snowflake variant path",
            sql="SELECT payload:labels['priority'] FROM events",
            dialect="snowflake",
            expected_sql="SELECT payload:labels['priority'] FROM events",
        ),
        PolyglotSqlNormalizationTestCase(
            description="preserves dynamic brackets outside Snowflake variant paths",
            sql="SELECT labels[TO_VARCHAR(item_id)] FROM events",
            dialect="snowflake",
            expected_sql="SELECT labels[TO_VARCHAR(item_id)] FROM events",
        ),
        PolyglotSqlNormalizationTestCase(
            description="preserves another dialect",
            sql="SELECT payload:labels[TO_VARCHAR(item_id)] FROM events",
            dialect="duckdb",
            expected_sql="SELECT payload:labels[TO_VARCHAR(item_id)] FROM events",
        ),
        PolyglotSqlNormalizationTestCase(
            description="preserves matching syntax in quoted text and comments",
            sql=(
                "SELECT 'payload:labels[TO_VARCHAR(item_id)]' AS text "
                "-- payload:labels[TO_VARCHAR(item_id)]\nFROM events"
            ),
            dialect="snowflake",
            expected_sql=(
                "SELECT 'payload:labels[TO_VARCHAR(item_id)]' AS text "
                "-- payload:labels[TO_VARCHAR(item_id)]\nFROM events"
            ),
        ),
        PolyglotSqlNormalizationTestCase(
            description="preserves Snowflake backslash-escaped quoted text",
            sql=r"SELECT 'it\'s ready' AS label",
            dialect="snowflake",
            expected_sql=r"SELECT 'it\'s ready' AS label",
        ),
        PolyglotSqlNormalizationTestCase(
            description="preserves Snowflake dollar-quoted text",
            sql="SELECT $$it's ready$$ AS label",
            dialect="snowflake",
            expected_sql="SELECT $$it's ready$$ AS label",
        ),
        PolyglotSqlNormalizationTestCase(
            description="rewrites a nested dynamic variant access",
            sql="SELECT labels[payload:groups[TO_VARCHAR(group_id)]] FROM events",
            dialect="snowflake",
            expected_sql="SELECT labels[GET(payload:groups, TO_VARCHAR(group_id))] FROM events",
        ),
        PolyglotSqlNormalizationTestCase(
            description="rewrites a dynamic variant access after whitespace",
            sql="SELECT payload:labels [TO_VARCHAR(item_id)] FROM events",
            dialect="snowflake",
            expected_sql="SELECT GET(payload:labels , TO_VARCHAR(item_id)) FROM events",
        ),
        PolyglotSqlNormalizationTestCase(
            description="rewrites a dynamic variant access after a block comment",
            sql="SELECT payload:labels/* item lookup */[TO_VARCHAR(item_id)] FROM events",
            dialect="snowflake",
            expected_sql=(
                "SELECT GET(payload:labels/* item lookup */, TO_VARCHAR(item_id)) FROM events"
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_sql_when_normalizing_for_polyglot_then_expected_sql_is_returned(
    test_case: PolyglotSqlNormalizationTestCase,
) -> None:
    assert (
        normalize_sql_for_polyglot(sql=test_case.sql, dialect=test_case.dialect)
        == test_case.expected_sql
    )
