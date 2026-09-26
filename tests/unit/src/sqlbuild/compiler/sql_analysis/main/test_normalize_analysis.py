from __future__ import annotations

import pytest

from sqlbuild.compiler.sql_analysis.main._normalize_analysis import normalize_analysis_sql
from tests.unit.src.sqlbuild.compiler.sql_analysis.main._test_types import (
    PolyglotSqlNormalizationTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    (
        PolyglotSqlNormalizationTestCase(
            description="package-qualified dbt reference becomes its model relation",
            sql='SELECT order_id FROM __dbt_ref("analytics", "dbt_orders")',
            dialect="duckdb",
            expected_sql="SELECT order_id FROM dbt_orders",
        ),
        PolyglotSqlNormalizationTestCase(
            description="bare dbt reference becomes its model relation",
            sql='SELECT order_id FROM __dbt_ref("dbt_orders")',
            dialect="duckdb",
            expected_sql="SELECT order_id FROM dbt_orders",
        ),
        PolyglotSqlNormalizationTestCase(
            description="project references keep their relation names",
            sql='SELECT order_id FROM __ref("orders") JOIN __source("raw_orders") USING (order_id)',
            dialect="duckdb",
            expected_sql="SELECT order_id FROM orders JOIN raw_orders USING (order_id)",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_reference_intrinsics_when_normalizing_for_analysis_then_relations_are_named(
    test_case: PolyglotSqlNormalizationTestCase,
) -> None:
    assert (
        normalize_analysis_sql(sql=test_case.sql, dialect=test_case.dialect)
        == test_case.expected_sql
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
