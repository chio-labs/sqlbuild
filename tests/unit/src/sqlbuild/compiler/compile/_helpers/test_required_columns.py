from __future__ import annotations

import pytest

from sqlbuild.compiler.compile._helpers.analysis.required_columns import (
    resolve_required_external_columns,
)
from sqlbuild.compiler.compile.models import CompiledLineageSourceFact, CompileSqlReference
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.references.types import SqlReferenceKind
from tests.unit.src.sqlbuild.compiler.compile._helpers._test_types import (
    RequiredExternalColumnsTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        RequiredExternalColumnsTestCase(
            description="resolves derived and generated CTE outputs",
            query_sql=(
                'WITH imported AS (SELECT * FROM __source("orders")), '
                "derived AS (SELECT order_id, UPPER(payload) AS normalized_status, "
                "CURRENT_TIMESTAMP AS loaded_at FROM imported), "
                "final AS (SELECT order_id, normalized_status, loaded_at FROM derived) "
                "SELECT order_id, normalized_status, loaded_at FROM final"
            ),
            references=(CompileSqlReference(SqlReferenceKind.SOURCE, "orders"),),
            expected_columns=(
                ("source", "orders", "order_id"),
                ("source", "orders", "payload"),
            ),
        ),
        RequiredExternalColumnsTestCase(
            description="resolves joins filters groups windows ordering and aliases",
            query_sql=(
                "WITH ranked AS ("
                "SELECT o.order_id, o.customer_id, o.amount, c.segment, "
                "ROW_NUMBER() OVER (PARTITION BY c.segment ORDER BY o.created_at) AS row_number "
                'FROM __source("orders") o '
                'JOIN __source("customers") c ON o.customer_id = c.customer_id '
                "WHERE o.active"
                "), grouped AS ("
                "SELECT segment, SUM(amount) AS total FROM ranked WHERE row_number = 1 "
                "GROUP BY segment HAVING SUM(amount) > 0"
                ") "
                "SELECT segment AS customer_segment, total FROM grouped ORDER BY customer_segment"
            ),
            references=(
                CompileSqlReference(SqlReferenceKind.SOURCE, "orders"),
                CompileSqlReference(SqlReferenceKind.SOURCE, "customers"),
            ),
            expected_columns=(
                ("source", "orders", "order_id"),
                ("source", "orders", "customer_id"),
                ("source", "orders", "amount"),
                ("source", "customers", "segment"),
                ("source", "orders", "created_at"),
                ("source", "customers", "customer_id"),
                ("source", "orders", "active"),
            ),
        ),
        RequiredExternalColumnsTestCase(
            description="resolves every set operation branch",
            query_sql=(
                "WITH combined AS ("
                'SELECT order_id, payload FROM __source("web_orders") '
                "UNION ALL "
                'SELECT order_id, payload FROM __source("partner_orders")'
                ") SELECT order_id, UPPER(payload) AS normalized_status FROM combined"
            ),
            references=(
                CompileSqlReference(SqlReferenceKind.SOURCE, "web_orders"),
                CompileSqlReference(SqlReferenceKind.SOURCE, "partner_orders"),
            ),
            expected_columns=(
                ("source", "web_orders", "order_id"),
                ("source", "web_orders", "payload"),
                ("source", "partner_orders", "order_id"),
                ("source", "partner_orders", "payload"),
            ),
        ),
        RequiredExternalColumnsTestCase(
            description="resolves derived tables and scalar subqueries",
            query_sql=(
                "SELECT staged.order_id, "
                '(SELECT MAX(priority) FROM __source("priorities")) AS maximum_priority '
                'FROM (SELECT order_id FROM __source("orders") WHERE active) staged'
            ),
            references=(
                CompileSqlReference(SqlReferenceKind.SOURCE, "priorities"),
                CompileSqlReference(SqlReferenceKind.SOURCE, "orders"),
            ),
            expected_columns=(
                ("source", "orders", "order_id"),
                ("source", "orders", "active"),
                ("source", "priorities", "priority"),
            ),
        ),
        RequiredExternalColumnsTestCase(
            description="resolves star replacement and rename inputs",
            query_sql=(
                "WITH staged AS ("
                "SELECT * REPLACE(UPPER(payload) AS status) RENAME(order_id AS id) "
                'FROM __source("orders")'
                ") SELECT id, status FROM staged"
            ),
            references=(CompileSqlReference(SqlReferenceKind.SOURCE, "orders"),),
            expected_columns=(
                ("source", "orders", "payload"),
                ("source", "orders", "order_id"),
            ),
        ),
        RequiredExternalColumnsTestCase(
            description="resolves using columns to both join inputs",
            query_sql=(
                "SELECT COUNT(*) AS match_count "
                'FROM __source("web_orders") '
                'JOIN __source("partner_orders") USING (order_id) '
                'CROSS JOIN __source("products")'
            ),
            references=(
                CompileSqlReference(SqlReferenceKind.SOURCE, "web_orders"),
                CompileSqlReference(SqlReferenceKind.SOURCE, "partner_orders"),
                CompileSqlReference(SqlReferenceKind.SOURCE, "products"),
            ),
            expected_columns=(
                ("source", "web_orders", "order_id"),
                ("source", "partner_orders", "order_id"),
            ),
        ),
        RequiredExternalColumnsTestCase(
            description="resolves output aliases without inventing source columns",
            query_sql=('SELECT order_id AS id FROM __source("orders") ORDER BY id'),
            references=(CompileSqlReference(SqlReferenceKind.SOURCE, "orders"),),
            expected_columns=(("source", "orders", "order_id"),),
        ),
        RequiredExternalColumnsTestCase(
            description="resolves correlated outer columns",
            query_sql=(
                "SELECT o.order_id "
                'FROM __source("orders") o '
                "WHERE EXISTS ("
                "SELECT 1 "
                'FROM __source("customers") c '
                "WHERE c.customer_id = o.customer_id"
                ")"
            ),
            references=(
                CompileSqlReference(SqlReferenceKind.SOURCE, "orders"),
                CompileSqlReference(SqlReferenceKind.SOURCE, "customers"),
            ),
            expected_columns=(
                ("source", "orders", "order_id"),
                ("source", "customers", "customer_id"),
                ("source", "orders", "customer_id"),
            ),
        ),
        RequiredExternalColumnsTestCase(
            description="preserves star passthrough across set operations",
            query_sql=(
                "WITH combined AS ("
                'SELECT * FROM __source("web_orders") '
                "UNION ALL "
                'SELECT * FROM __source("partner_orders")'
                ") SELECT order_id FROM combined"
            ),
            references=(
                CompileSqlReference(SqlReferenceKind.SOURCE, "web_orders"),
                CompileSqlReference(SqlReferenceKind.SOURCE, "partner_orders"),
            ),
            expected_columns=(
                ("source", "web_orders", "order_id"),
                ("source", "partner_orders", "order_id"),
            ),
        ),
        RequiredExternalColumnsTestCase(
            description="does not resolve generated local columns against an outer scope",
            query_sql=(
                "WITH generated AS (SELECT 1 AS status) "
                "SELECT o.order_id "
                'FROM __source("orders") o '
                "WHERE EXISTS (SELECT 1 FROM generated WHERE status = 1)"
            ),
            references=(CompileSqlReference(SqlReferenceKind.SOURCE, "orders"),),
            expected_columns=(("source", "orders", "order_id"),),
        ),
        RequiredExternalColumnsTestCase(
            description="prefers input columns over aliases in grouping clauses",
            query_sql=(
                'SELECT 1 AS status, COUNT(*) AS row_count FROM __source("orders") GROUP BY status'
            ),
            references=(CompileSqlReference(SqlReferenceKind.SOURCE, "orders"),),
            expected_columns=(("source", "orders", "status"),),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_query_when_resolving_required_columns_then_returns_external_reads(
    test_case: RequiredExternalColumnsTestCase,
) -> None:
    result: tuple[CompiledLineageSourceFact, ...] = resolve_required_external_columns(
        query_sql=test_case.query_sql,
        references=test_case.references,
        dialect="duckdb",
    )

    received: tuple[tuple[str, str, str], ...] = tuple(
        (
            CompiledResourceType(source.resource_type).value,
            source.resource_name,
            source.column_name,
        )
        for source in result
    )
    assert len(received) == len(test_case.expected_columns)
    assert frozenset(received) == frozenset(test_case.expected_columns)


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
