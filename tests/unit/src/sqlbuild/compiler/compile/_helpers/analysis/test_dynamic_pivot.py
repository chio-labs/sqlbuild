from __future__ import annotations

import pytest

from sqlbuild.compiler.compile._helpers.analysis.dynamic_pivot import (
    analyze_dynamic_column_contract,
)
from sqlbuild.compiler.compile.models import DynamicColumnContractProof
from sqlbuild.spec.contracts.models import SchemaDynamicColumnFamily
from tests.unit.src.sqlbuild.compiler.compile._helpers.analysis._test_types import (
    DynamicPivotAnalysisTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    (
        DynamicPivotAnalysisTestCase(
            description="Snowflake ANY pivot is compiler proven",
            dialect="snowflake",
            query_sql=(
                "WITH pivot_input AS ("
                "SELECT customer_id, category, amount, country FROM order_amounts"
                ") SELECT * FROM pivot_input "
                "PIVOT(MAX(amount) FOR category IN (ANY ORDER BY category))"
            ),
            expected_proven=True,
            expected_fixed_columns=("customer_id", "country"),
        ),
        DynamicPivotAnalysisTestCase(
            description="static pivot list requires exact columns",
            dialect="snowflake",
            query_sql=(
                "SELECT * FROM order_amounts PIVOT(MAX(amount) FOR category IN ('books', 'games'))"
            ),
            expected_proven=False,
            expected_failure_fragment="static pivot values",
            expected_family_types=(),
        ),
        DynamicPivotAnalysisTestCase(
            description="unsupported adapter rejects dynamic family",
            dialect="bigquery",
            query_sql="SELECT * FROM order_amounts",
            expected_proven=False,
            expected_failure_fragment="does not support compiler-proven dynamic pivots",
            expected_family_types=(),
        ),
        DynamicPivotAnalysisTestCase(
            description="ordinary dependency wildcard is not a pivot family",
            dialect="snowflake",
            query_sql='SELECT * FROM __ref("order_amounts")',
            expected_proven=False,
            expected_failure_fragment="must redeclare the upstream families exactly",
            expected_family_types=(),
        ),
        DynamicPivotAnalysisTestCase(
            description="partial upstream declaration cannot prove fixed shape",
            dialect="snowflake",
            query_sql=(
                "SELECT * FROM partial_order_amounts PIVOT(MAX(amount) FOR category IN (ANY))"
            ),
            expected_proven=False,
            expected_failure_fragment="authoritative, explicit schema",
            expected_family_types=(),
        ),
        DynamicPivotAnalysisTestCase(
            description="star replacement cannot masquerade as passthrough",
            dialect="snowflake",
            query_sql=(
                "WITH pivoted AS (SELECT * FROM order_amounts "
                "PIVOT(MAX(amount) FOR category IN (ANY))) "
                "SELECT * REPLACE (CAST(99 AS VARCHAR) AS customer_id) FROM pivoted"
            ),
            expected_proven=False,
            expected_failure_fragment="wildcard projection",
            expected_family_types=(),
        ),
        DynamicPivotAnalysisTestCase(
            description="CTE output aliases cannot silently rename fixed columns",
            dialect="snowflake",
            query_sql=(
                "WITH order_amounts(customer_id, category, amount, extra) AS ("
                "SELECT customer_id, category, amount, country FROM order_amounts"
                ") SELECT * FROM order_amounts "
                "PIVOT(MAX(amount) FOR category IN (ANY))"
            ),
            expected_proven=False,
            expected_failure_fragment="authoritative, explicit schema",
            expected_family_types=(),
        ),
        DynamicPivotAnalysisTestCase(
            description="explicit cast in pivot input establishes value type",
            dialect="snowflake",
            query_sql=(
                "WITH pivot_input AS ("
                "SELECT customer_id, category, CAST(amount AS DECIMAL(12,2)) AS amount, country "
                "FROM order_amounts"
                ") SELECT * FROM pivot_input "
                "PIVOT(MAX(amount) FOR category IN (ANY))"
            ),
            expected_proven=True,
            expected_fixed_columns=("customer_id", "country"),
            expected_family_types=("DECIMAL(12, 2)",),
        ),
        DynamicPivotAnalysisTestCase(
            description="widening aggregate input cast does not prove output type",
            dialect="duckdb",
            query_sql=(
                "PIVOT order_amounts ON category USING SUM(CAST(amount AS INTEGER)) "
                "GROUP BY customer_id"
            ),
            expected_proven=True,
            expected_fixed_columns=("customer_id",),
            expected_family_types=(None,),
            aggregate="SUM",
        ),
        DynamicPivotAnalysisTestCase(
            description="compound pivot expression cannot disappear from shape proof",
            dialect="duckdb",
            query_sql=(
                "PIVOT order_amounts ON category, UPPER(country) USING MAX(amount) "
                "GROUP BY customer_id"
            ),
            expected_proven=False,
            expected_failure_fragment="direct column references",
            expected_family_types=(),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_dynamic_family_when_analyzing_output_then_requires_supported_closed_shape(
    test_case: DynamicPivotAnalysisTestCase,
) -> None:
    proof: DynamicColumnContractProof | None = analyze_dynamic_column_contract(
        query_sql=test_case.query_sql,
        dialect=test_case.dialect,
        families=(
            SchemaDynamicColumnFamily(
                name="category_amounts",
                pivot_column="category",
                value_column="amount",
                aggregate=test_case.aggregate,
                type="DECIMAL(12,2)",
            ),
        ),
        column_types_by_table={
            "order_amounts": {
                "customer_id": "INTEGER",
                "category": "VARCHAR",
                "amount": "DECIMAL(12,2)",
                "country": "VARCHAR",
            },
            "partial_order_amounts": {
                "customer_id": "INTEGER",
                "category": "VARCHAR",
                "amount": "DECIMAL(12,2)",
            },
        },
        authoritative_column_types_by_table={
            "order_amounts": {
                "customer_id": "INTEGER",
                "category": "VARCHAR",
                "amount": "DECIMAL(12,2)",
                "country": "VARCHAR",
            }
        },
        column_nullability_by_table={},
        dynamic_families_by_table={},
    )

    assert proof is not None
    assert proof.output_proven is test_case.expected_proven
    assert tuple(column.name for column in proof.fixed_columns) == test_case.expected_fixed_columns
    assert tuple(family.inferred_type for family in proof.families) == (
        test_case.expected_family_types
    )
    assert test_case.expected_failure_fragment in (proof.failure_reason or "")
