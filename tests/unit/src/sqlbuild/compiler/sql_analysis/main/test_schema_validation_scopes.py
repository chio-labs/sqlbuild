from __future__ import annotations

import pytest

from sqlbuild.compiler.sql_analysis.main._schema_validation import get_schema_validations
from sqlbuild.compiler.sql_analysis.models import SqlBindingResult, SqlSchemaValidationRequest
from tests.unit.src.sqlbuild.compiler.sql_analysis.main._test_types import (
    SchemaValidationScopeTestCase,
)

_SUPPORTED_SCHEMA_DIALECTS: tuple[str, ...] = (
    "generic",
    "snowflake",
    "duckdb",
    "bigquery",
    "databricks",
    "postgres",
    "tsql",
)


@pytest.mark.parametrize(
    "test_case",
    [
        SchemaValidationScopeTestCase(
            description="qualified columns remain local to their outer query scope",
            query_sql=(
                "WITH selected_orders AS (SELECT id FROM orders), "
                "selected_returns AS (SELECT id FROM returns) "
                "SELECT selected_orders.id FROM selected_orders "
                "JOIN selected_returns ON selected_orders.id = selected_returns.id"
            ),
            schema={"orders": {"id": "integer"}, "returns": {"id": "integer"}},
            dialects=_SUPPORTED_SCHEMA_DIALECTS,
            expected_diagnostic_count=0,
        ),
        SchemaValidationScopeTestCase(
            description="correlated subquery resolves its outer alias",
            query_sql=(
                "SELECT outer_orders.id FROM orders outer_orders "
                "WHERE EXISTS (SELECT 1 FROM returns inner_returns "
                "WHERE inner_returns.order_id = outer_orders.id)"
            ),
            schema={
                "orders": {"id": "integer"},
                "returns": {"order_id": "integer"},
            },
            dialects=_SUPPORTED_SCHEMA_DIALECTS,
            expected_diagnostic_count=0,
        ),
        SchemaValidationScopeTestCase(
            description="subsequent CTE resolves a prior projected alias",
            query_sql=(
                "WITH derived AS (SELECT amount AS derived_amount FROM orders), "
                "next_step AS (SELECT derived_amount FROM derived) "
                "SELECT derived_amount FROM next_step"
            ),
            schema={"orders": {"amount": "decimal"}},
            dialects=_SUPPORTED_SCHEMA_DIALECTS,
            expected_diagnostic_count=0,
        ),
        SchemaValidationScopeTestCase(
            description="window ordering resolves a prior CTE projection",
            query_sql=(
                "WITH scored AS (SELECT customer_id, amount AS score FROM orders), "
                "ranked AS (SELECT customer_id, ROW_NUMBER() OVER ("
                "PARTITION BY customer_id ORDER BY score DESC) AS row_number FROM scored) "
                "SELECT customer_id FROM ranked"
            ),
            schema={
                "orders": {"customer_id": "integer", "amount": "decimal"},
            },
            dialects=_SUPPORTED_SCHEMA_DIALECTS,
            expected_diagnostic_count=0,
        ),
        SchemaValidationScopeTestCase(
            description="nested qualify resolves directly projected columns",
            query_sql=(
                "WITH prepared_orders AS (SELECT customer_id, id AS order_id, amount "
                "FROM orders), selected_orders AS (SELECT customer_id, order_id, amount "
                "FROM (SELECT customer_id, order_id, amount FROM prepared_orders "
                "QUALIFY ROW_NUMBER() OVER (PARTITION BY customer_id "
                "ORDER BY order_id) = 1)) SELECT customer_id, order_id FROM selected_orders"
            ),
            schema={
                "orders": {
                    "id": "integer",
                    "customer_id": "integer",
                    "amount": "decimal",
                },
            },
            dialects=("snowflake",),
            expected_diagnostic_count=0,
        ),
        SchemaValidationScopeTestCase(
            description="join using resolves a projected CTE column on both sides",
            query_sql=(
                "WITH eligible_orders AS (SELECT order_id FROM orders), "
                "prepared_orders AS (SELECT orders.* FROM orders "
                "JOIN eligible_orders USING (order_id)) "
                "SELECT customer_id FROM prepared_orders"
            ),
            schema={
                "orders": {
                    "order_id": "integer",
                    "customer_id": "integer",
                },
            },
            dialects=_SUPPORTED_SCHEMA_DIALECTS,
            expected_diagnostic_count=0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_nested_query_scopes_when_validating_complete_schema_then_resolves_columns(
    test_case: SchemaValidationScopeTestCase,
) -> None:
    results: tuple[SqlBindingResult, ...] = get_schema_validations(
        requests=tuple(
            SqlSchemaValidationRequest(
                sql=test_case.query_sql,
                dialect=dialect,
                schema=test_case.schema,
            )
            for dialect in test_case.dialects
        )
    )

    assert len(results) == len(test_case.dialects)
    assert sum(len(result.diagnostics) for result in results) == test_case.expected_diagnostic_count
