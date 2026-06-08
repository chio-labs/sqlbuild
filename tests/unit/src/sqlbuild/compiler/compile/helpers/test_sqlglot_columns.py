from __future__ import annotations

import pytest

from sqlbuild.adapter.shared.models import ExpressionInferenceProfile
from sqlbuild.compiler.compile.helpers.sqlglot_columns import (
    analyze_columns_and_lineage_with_polyglot,
    infer_columns_with_sqlglot,
    substitute_placeholder_defaults,
)
from sqlbuild.compiler.compile.models.core import (
    CompiledLineageColumnFact,
    CompiledLineageSourceFact,
    CompileSqlReference,
    InferredColumn,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.lineage.types import (
    ColumnLineageConfidence,
    ColumnTransformKind,
    InferredNullability,
)
from sqlbuild.shared.types import SqlReferenceKind
from tests.unit.src.sqlbuild.compiler.compile.helpers._test_types import (
    InferColumnsTestCase,
    PolyglotAnalysisTestCase,
    SubstitutePlaceholderDefaultsTestCase,
)

INFER_COLUMNS_TEST_CASES: list[InferColumnsTestCase] = [
    InferColumnsTestCase(
        description="extracts simple column names from select",
        query_sql='SELECT order_id, status FROM __ref("orders")',
        expected_columns=(
            InferredColumn(name="order_id"),
            InferredColumn(name="status"),
        ),
    ),
    InferColumnsTestCase(
        description="extracts cast type from explicit cast",
        query_sql='SELECT CAST(amount AS DECIMAL(10, 2)) AS amount FROM __ref("orders")',
        expected_columns=(InferredColumn(name="amount", type="DECIMAL(10, 2)"),),
    ),
    InferColumnsTestCase(
        description="extracts cast type from try cast",
        query_sql='SELECT TRY_CAST(x AS INT) AS val FROM __ref("orders")',
        expected_columns=(InferredColumn(name="val", type="INT"),),
    ),
    InferColumnsTestCase(
        description="returns empty tuple for select star",
        query_sql='SELECT * FROM __ref("orders")',
        expected_columns=(),
    ),
    InferColumnsTestCase(
        description="extracts columns from aliased table references",
        query_sql=(
            'SELECT o.order_id, o.status FROM __ref("orders") o '
            'JOIN __ref("items") i ON o.id = i.order_id'
        ),
        expected_columns=(
            InferredColumn(name="order_id"),
            InferredColumn(name="status"),
        ),
    ),
    InferColumnsTestCase(
        description="extracts aliased expression names",
        query_sql='SELECT order_id, price * qty AS total FROM __ref("orders")',
        expected_columns=(
            InferredColumn(name="order_id"),
            InferredColumn(name="total"),
        ),
    ),
    InferColumnsTestCase(
        description="extracts columns through CTE chain",
        query_sql=(
            "WITH base AS ("
            '  SELECT order_id, CAST(amount AS FLOAT) AS amount FROM __ref("orders")'
            ") "
            "SELECT order_id, amount FROM base"
        ),
        expected_columns=(
            InferredColumn(name="order_id"),
            InferredColumn(name="amount"),
        ),
    ),
    InferColumnsTestCase(
        description="extracts columns from union taking first branch",
        query_sql=(
            'SELECT order_id, status FROM __ref("orders") '
            "UNION ALL "
            'SELECT return_id, status FROM __ref("returns")'
        ),
        expected_columns=(
            InferredColumn(name="order_id"),
            InferredColumn(name="status"),
        ),
    ),
    InferColumnsTestCase(
        description="handles source references",
        query_sql='SELECT id, name FROM __source("stripe__payments")',
        expected_columns=(
            InferredColumn(name="id"),
            InferredColumn(name="name"),
        ),
    ),
    InferColumnsTestCase(
        description="handles dbt ref references",
        query_sql='SELECT id, name FROM __dbt_ref("stg_orders")',
        expected_columns=(
            InferredColumn(name="id"),
            InferredColumn(name="name"),
        ),
    ),
    InferColumnsTestCase(
        description="extracts columns from deep cte chain with window functions",
        query_sql=(
            "WITH base AS ("
            '  SELECT order_id, customer_id, amount FROM __ref("stg_orders")'
            "), "
            "with_metrics AS ("
            "  SELECT order_id, customer_id, amount, "
            "    SUM(amount) OVER (PARTITION BY customer_id) AS total, "
            "    ROW_NUMBER() OVER (ORDER BY amount DESC) AS rn "
            "  FROM base"
            ") "
            "SELECT order_id, customer_id, amount, total, rn FROM with_metrics"
        ),
        expected_columns=(
            InferredColumn(name="order_id"),
            InferredColumn(name="customer_id"),
            InferredColumn(name="amount"),
            InferredColumn(name="total"),
            InferredColumn(name="rn"),
        ),
    ),
    InferColumnsTestCase(
        description="skips unaliased non-column expressions",
        query_sql='SELECT order_id, 1 + 2 FROM __ref("orders")',
        expected_columns=(InferredColumn(name="order_id"),),
    ),
    InferColumnsTestCase(
        description="returns none for unparseable sql",
        query_sql="NOT VALID SQL {{{{ }}}}",
        expected_columns=None,
    ),
    InferColumnsTestCase(
        description="infers safe literal nullability",
        query_sql="SELECT 1 AS one, NULL AS missing",
        expected_columns=(
            InferredColumn(name="one", nullability=InferredNullability.NON_NULL),
            InferredColumn(name="missing", nullability=InferredNullability.NULLABLE),
        ),
    ),
    InferColumnsTestCase(
        description="inherits direct passthrough nullability from known table facts",
        query_sql='SELECT order_id, status FROM __ref("orders")',
        column_nullability_by_table={
            "orders": {
                "order_id": InferredNullability.NON_NULL,
                "status": InferredNullability.UNKNOWN,
            }
        },
        expected_columns=(
            InferredColumn(name="order_id", nullability=InferredNullability.NON_NULL),
            InferredColumn(name="status", nullability=InferredNullability.UNKNOWN),
        ),
    ),
    InferColumnsTestCase(
        description="marks right side of left join nullable",
        query_sql=(
            'SELECT o.order_id, c.name FROM __ref("orders") o '
            'LEFT JOIN __ref("customers") c ON o.customer_id = c.customer_id'
        ),
        column_nullability_by_table={
            "orders": {"order_id": InferredNullability.NON_NULL},
            "customers": {"name": InferredNullability.NON_NULL},
        },
        expected_columns=(
            InferredColumn(name="order_id", nullability=InferredNullability.NON_NULL),
            InferredColumn(name="name", nullability=InferredNullability.NULLABLE),
        ),
    ),
    InferColumnsTestCase(
        description="marks left side of right join nullable",
        query_sql=(
            'SELECT o.order_id, c.name FROM __ref("orders") o '
            'RIGHT JOIN __ref("customers") c ON o.customer_id = c.customer_id'
        ),
        column_nullability_by_table={
            "orders": {"order_id": InferredNullability.NON_NULL},
            "customers": {"name": InferredNullability.NON_NULL},
        },
        expected_columns=(
            InferredColumn(name="order_id", nullability=InferredNullability.NULLABLE),
            InferredColumn(name="name", nullability=InferredNullability.NON_NULL),
        ),
    ),
    InferColumnsTestCase(
        description="marks both sides of full join nullable",
        query_sql=(
            'SELECT o.order_id, c.name FROM __ref("orders") o '
            'FULL JOIN __ref("customers") c ON o.customer_id = c.customer_id'
        ),
        column_nullability_by_table={
            "orders": {"order_id": InferredNullability.NON_NULL},
            "customers": {"name": InferredNullability.NON_NULL},
        },
        expected_columns=(
            InferredColumn(name="order_id", nullability=InferredNullability.NULLABLE),
            InferredColumn(name="name", nullability=InferredNullability.NULLABLE),
        ),
    ),
    InferColumnsTestCase(
        description="infers count as non null",
        query_sql='SELECT COUNT(*) AS order_count FROM __ref("orders")',
        expected_columns=(
            InferredColumn(name="order_count", nullability=InferredNullability.NON_NULL),
        ),
    ),
    InferColumnsTestCase(
        description="infers coalesce with literal fallback as non null",
        query_sql="SELECT COALESCE(status, 'unknown') AS status FROM __ref(\"orders\")",
        expected_columns=(InferredColumn(name="status", nullability=InferredNullability.NON_NULL),),
    ),
    InferColumnsTestCase(
        description="preserves cast input nullability",
        query_sql='SELECT CAST(order_id AS BIGINT) AS order_id FROM __ref("orders")',
        column_nullability_by_table={"orders": {"order_id": InferredNullability.NON_NULL}},
        expected_columns=(
            InferredColumn(
                name="order_id", type="BIGINT", nullability=InferredNullability.NON_NULL
            ),
        ),
    ),
    InferColumnsTestCase(
        description="leaves arbitrary expressions unknown",
        query_sql='SELECT quantity * price AS total FROM __ref("orders")',
        column_nullability_by_table={
            "orders": {
                "quantity": InferredNullability.NON_NULL,
                "price": InferredNullability.NON_NULL,
            }
        },
        expected_columns=(InferredColumn(name="total"),),
    ),
    InferColumnsTestCase(
        description="leaves set operation nullability unknown",
        query_sql="SELECT 1 AS value UNION ALL SELECT NULL AS value",
        expected_columns=(InferredColumn(name="value"),),
    ),
    InferColumnsTestCase(
        description="uses adapter function nullability rule",
        query_sql="SELECT LOWER('READY') AS status",
        inference_profile=ExpressionInferenceProfile(
            function_nullability_rules={
                "LOWER": lambda args: (
                    InferredNullability.NON_NULL
                    if args == (InferredNullability.NON_NULL,)
                    else InferredNullability.UNKNOWN
                ),
            }
        ),
        expected_columns=(InferredColumn(name="status", nullability=InferredNullability.NON_NULL),),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    INFER_COLUMNS_TEST_CASES,
    ids=[case.description for case in INFER_COLUMNS_TEST_CASES],
)
def test_given_query_sql_when_inferring_columns_then_returns_expected(
    test_case: InferColumnsTestCase,
) -> None:
    result: tuple[InferredColumn, ...] | None = infer_columns_with_sqlglot(
        query_sql=test_case.query_sql,
        column_nullability_by_table=test_case.column_nullability_by_table,
        inference_profile=test_case.inference_profile,
    )

    assert result == test_case.expected_columns


@pytest.mark.parametrize(
    "test_case",
    [
        PolyglotAnalysisTestCase(
            description="extracts compact direct lineage facts from unqualified refs",
            query_sql='SELECT order_id FROM __ref("orders")',
            references=(CompileSqlReference(SqlReferenceKind.REF, "orders"),),
            expected_columns=(InferredColumn(name="order_id"),),
            expected_lineage_columns=(
                CompiledLineageColumnFact(
                    output_column="order_id",
                    upstream_columns=(
                        CompiledLineageSourceFact(
                            resource_type=CompiledResourceType.MODEL,
                            resource_name="orders",
                            column_name="order_id",
                        ),
                    ),
                    transform_kind=ColumnTransformKind.DIRECT,
                    confidence=ColumnLineageConfidence.MEDIUM,
                ),
            ),
            expected_has_star=False,
        )
    ],
    ids=["extracts compact direct lineage facts from unqualified refs"],
)
def test_given_ref_query_when_analyzing_columns_and_lineage_then_returns_compact_facts(
    test_case: PolyglotAnalysisTestCase,
) -> None:
    result: (
        tuple[tuple[InferredColumn, ...] | None, tuple[CompiledLineageColumnFact, ...], bool] | bool
    ) = analyze_columns_and_lineage_with_polyglot(
        query_sql=test_case.query_sql,
        references=test_case.references,
    )

    assert isinstance(result, tuple)
    columns, lineage_columns, has_star = result
    assert columns == test_case.expected_columns
    assert lineage_columns == test_case.expected_lineage_columns
    assert has_star is test_case.expected_has_star


SUBSTITUTE_PLACEHOLDER_TEST_CASES: list[SubstitutePlaceholderDefaultsTestCase] = [
    SubstitutePlaceholderDefaultsTestCase(
        description="substitutes single placeholder",
        query_sql="SELECT * FROM t WHERE d >= @@@partition_start",
        placeholders={"partition_start": "'2020-01-01'"},
        expected_sql="SELECT * FROM t WHERE d >= '2020-01-01'",
    ),
    SubstitutePlaceholderDefaultsTestCase(
        description="substitutes multiple placeholders",
        query_sql="SELECT * FROM t WHERE d >= @@@start AND d < @@@end",
        placeholders={"start": "'2020-01-01'", "end": "'2099-12-31'"},
        expected_sql="SELECT * FROM t WHERE d >= '2020-01-01' AND d < '2099-12-31'",
    ),
    SubstitutePlaceholderDefaultsTestCase(
        description="returns sql unchanged when no placeholders defined",
        query_sql="SELECT * FROM t WHERE d >= @@@start",
        placeholders={},
        expected_sql="SELECT * FROM t WHERE d >= @@@start",
    ),
    SubstitutePlaceholderDefaultsTestCase(
        description="returns sql unchanged when no placeholders in sql",
        query_sql="SELECT * FROM t",
        placeholders={"x": "'1'"},
        expected_sql="SELECT * FROM t",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    SUBSTITUTE_PLACEHOLDER_TEST_CASES,
    ids=[case.description for case in SUBSTITUTE_PLACEHOLDER_TEST_CASES],
)
def test_given_sql_with_placeholders_when_substituting_then_returns_expected(
    test_case: SubstitutePlaceholderDefaultsTestCase,
) -> None:
    result: str = substitute_placeholder_defaults(test_case.query_sql, test_case.placeholders)

    assert result == test_case.expected_sql
