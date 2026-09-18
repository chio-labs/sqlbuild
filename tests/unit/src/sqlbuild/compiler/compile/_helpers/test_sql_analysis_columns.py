from __future__ import annotations

import pytest
from polyglot_sql import ParseError

from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.compiler.compile._helpers.analysis.columns import (
    analyze_columns_and_lineage_with_polyglot,
    import_polyglot_sql,
    infer_columns_with_sql_analysis,
    substitute_placeholder_defaults,
)
from sqlbuild.compiler.compile.models import (
    CompiledLineageColumnFact,
    CompiledLineageSourceFact,
    CompileSqlReference,
    InferredColumn,
    PolyglotAnalysisResult,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.lineage.types import (
    ColumnLineageConfidence,
    ColumnTransformKind,
    InferredNullability,
)
from sqlbuild.compiler.references.types import SqlReferenceKind
from tests.unit.src.sqlbuild.compiler.compile._helpers._test_types import (
    InferColumnsTestCase,
    PolyglotAnalysisTestCase,
    SubstitutePlaceholderDefaultsTestCase,
    UnexpectedAnalysisFailureTestCase,
)
from tests.unit.src.sqlbuild.compiler.compile._helpers.helpers import direct_orders_lineage


@pytest.mark.parametrize(
    "test_case",
    [
        InferColumnsTestCase(
            description="extracts simple column names from select",
            query_sql='SELECT order_id, status FROM __ref("orders")',
            expected_columns=(
                InferredColumn(name="order_id"),
                InferredColumn(name="status"),
            ),
        ),
        InferColumnsTestCase(
            description="extracts a commented qualified column without a self alias",
            query_sql=(
                "SELECT orders.order_id,\n"
                "-- Current customer status.\n"
                'orders.status\nFROM __ref("orders") AS orders'
            ),
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
            description="preserves varchar length from explicit cast",
            query_sql='SELECT CAST(status AS VARCHAR(3)) AS status FROM __ref("orders")',
            expected_columns=(InferredColumn(name="status", type="VARCHAR(3)"),),
        ),
        InferColumnsTestCase(
            description="extracts cast type from try cast",
            query_sql='SELECT TRY_CAST(x AS INT) AS val FROM __ref("orders")',
            expected_columns=(InferredColumn(name="val", type="INT"),),
        ),
        InferColumnsTestCase(
            description="preserves timezone metadata for Snowflake timestamp casts",
            query_sql=(
                "SELECT source_ts::TIMESTAMP_TZ AS message_timestamp, "
                'NULL::NUMBER AS placeholder FROM __ref("orders")'
            ),
            expected_columns=(
                InferredColumn(name="message_timestamp", type="TIMESTAMPTZ"),
                InferredColumn(
                    name="placeholder", type="DECIMAL", nullability=InferredNullability.NULLABLE
                ),
            ),
            inference_profile=ExpressionInferenceProfile(sql_analysis_dialect="snowflake"),
        ),
        InferColumnsTestCase(
            description="extracts Snowflake custom cast target names",
            query_sql=(
                "SELECT "
                "CAST(NULL AS VARIANT) AS variant_value, "
                "CAST(NULL AS NUMBER) AS number_value, "
                "CAST(NULL AS NUMBER(10, 2)) AS sized_number_value, "
                "CAST(NULL AS OBJECT) AS object_value, "
                "CAST(NULL AS ARRAY) AS array_value, "
                "CAST(NULL AS ARRAY(VARCHAR)) AS typed_array_value, "
                "CAST(NULL AS DECIMAL) AS decimal_value, "
                "CAST(NULL AS DECIMAL(10, 2)) AS sized_decimal_value, "
                "CAST(NULL AS JSON) AS json_value, "
                "TRY_CAST(NULL AS VARIANT) AS try_variant_value"
            ),
            expected_columns=(
                InferredColumn(
                    name="variant_value", type="VARIANT", nullability=InferredNullability.NULLABLE
                ),
                InferredColumn(
                    name="number_value", type="NUMBER", nullability=InferredNullability.NULLABLE
                ),
                InferredColumn(
                    name="sized_number_value",
                    type="NUMBER(10, 2)",
                    nullability=InferredNullability.NULLABLE,
                ),
                InferredColumn(
                    name="object_value", type="OBJECT", nullability=InferredNullability.NULLABLE
                ),
                InferredColumn(
                    name="array_value", type="ARRAY", nullability=InferredNullability.NULLABLE
                ),
                InferredColumn(
                    name="typed_array_value", type="ARRAY", nullability=InferredNullability.NULLABLE
                ),
                InferredColumn(
                    name="decimal_value", type="DECIMAL", nullability=InferredNullability.NULLABLE
                ),
                InferredColumn(
                    name="sized_decimal_value",
                    type="DECIMAL(10, 2)",
                    nullability=InferredNullability.NULLABLE,
                ),
                InferredColumn(
                    name="json_value", type="JSON", nullability=InferredNullability.NULLABLE
                ),
                InferredColumn(name="try_variant_value", type="VARIANT"),
            ),
            inference_profile=ExpressionInferenceProfile(sql_analysis_dialect="snowflake"),
        ),
        InferColumnsTestCase(
            description="uses adapter return types for Snowflake conversion functions",
            query_sql=(
                "SELECT "
                "TO_VARIANT(raw_value) AS variant_value, "
                "TO_ARRAY(raw_value) AS array_value, "
                "TO_OBJECT(raw_value) AS object_value, "
                "UNKNOWN_FUNCTION(raw_value) AS unknown_value"
            ),
            expected_columns=(
                InferredColumn(name="variant_value", type="VARIANT"),
                InferredColumn(name="array_value", type="ARRAY"),
                InferredColumn(name="object_value", type="OBJECT"),
                InferredColumn(name="unknown_value"),
            ),
            inference_profile=ExpressionInferenceProfile(
                sql_analysis_dialect="snowflake",
                function_return_types={
                    "TO_ARRAY": "ARRAY",
                    "TO_OBJECT": "OBJECT",
                    "TO_VARIANT": "VARIANT",
                },
            ),
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
                InferredColumn(name="amount", type="FLOAT"),
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
            description="refines qualified filtered output nullability",
            query_sql=(
                'SELECT o.order_id FROM __ref("orders") AS o WHERE (O.order_id IS NOT NULL)'
            ),
            column_nullability_by_table={"orders": {"order_id": InferredNullability.NULLABLE}},
            expected_columns=(
                InferredColumn(
                    name="order_id",
                    nullability=InferredNullability.NON_NULL,
                ),
            ),
        ),
        InferColumnsTestCase(
            description="does not refine nullability through a disjunction",
            query_sql=(
                'SELECT order_id FROM __ref("orders") '
                "WHERE order_id IS NOT NULL OR status = 'ready'"
            ),
            column_nullability_by_table={
                "orders": {
                    "order_id": InferredNullability.NULLABLE,
                    "status": InferredNullability.NON_NULL,
                }
            },
            expected_columns=(
                InferredColumn(
                    name="order_id",
                    nullability=InferredNullability.NULLABLE,
                ),
            ),
        ),
        InferColumnsTestCase(
            description="does not leak a filtered self join alias",
            query_sql=(
                "WITH selected AS ("
                'SELECT b.order_id FROM __ref("orders") AS a '
                'CROSS JOIN __ref("orders") AS b '
                "WHERE a.order_id IS NOT NULL"
                ") SELECT order_id FROM selected"
            ),
            column_nullability_by_table={"orders": {"order_id": InferredNullability.NULLABLE}},
            expected_columns=(
                InferredColumn(
                    name="order_id",
                    nullability=InferredNullability.NULLABLE,
                ),
            ),
        ),
        InferColumnsTestCase(
            description="does not leak an outer filter into a CTE",
            query_sql=(
                "WITH selected AS ("
                'SELECT order_id FROM __ref("orders")'
                ") SELECT selected.order_id FROM selected "
                'CROSS JOIN __ref("orders") AS o '
                "WHERE o.order_id IS NOT NULL"
            ),
            column_nullability_by_table={"orders": {"order_id": InferredNullability.NULLABLE}},
            expected_columns=(
                InferredColumn(
                    name="order_id",
                    nullability=InferredNullability.NULLABLE,
                ),
            ),
        ),
        InferColumnsTestCase(
            description="refines a filtered outer join column",
            query_sql=(
                'SELECT c.customer_id FROM __ref("orders") AS o '
                'LEFT JOIN __ref("customers") AS c '
                "ON o.order_id = c.customer_id "
                "WHERE c.customer_id IS NOT NULL"
            ),
            column_nullability_by_table={
                "orders": {"order_id": InferredNullability.NON_NULL},
                "customers": {"customer_id": InferredNullability.NON_NULL},
            },
            expected_columns=(
                InferredColumn(
                    name="customer_id",
                    nullability=InferredNullability.NON_NULL,
                ),
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
            expected_columns=(
                InferredColumn(name="status", nullability=InferredNullability.NON_NULL),
            ),
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
            description="infers null predicates as non-null booleans",
            query_sql=('SELECT status IS NOT NULL AS has_status FROM __ref("orders")'),
            column_nullability_by_table={"orders": {"status": InferredNullability.NULLABLE}},
            expected_columns=(
                InferredColumn(
                    name="has_status",
                    type="BOOLEAN",
                    nullability=InferredNullability.NON_NULL,
                ),
            ),
        ),
        InferColumnsTestCase(
            description="refines filtered CTE output nullability",
            query_sql=(
                "WITH mapped AS ("
                'SELECT order_id FROM __ref("orders")'
                "), final AS ("
                "SELECT CAST(order_id AS VARCHAR) AS order_id FROM mapped "
                "WHERE order_id IS NOT NULL"
                ") SELECT order_id FROM final"
            ),
            column_nullability_by_table={"orders": {"order_id": InferredNullability.NULLABLE}},
            expected_columns=(
                InferredColumn(
                    name="order_id",
                    type="TEXT",
                    nullability=InferredNullability.NON_NULL,
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
            expected_columns=(
                InferredColumn(name="status", nullability=InferredNullability.NON_NULL),
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_query_sql_when_inferring_columns_then_returns_expected(
    test_case: InferColumnsTestCase,
) -> None:
    result: tuple[InferredColumn, ...] | None = infer_columns_with_sql_analysis(
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
                    confidence=ColumnLineageConfidence.HIGH,
                ),
            ),
            expected_has_star=False,
        ),
        PolyglotAnalysisTestCase(
            description="refines a compact filtered column across whitespace",
            query_sql=('SELECT order_id FROM __ref("orders") WHERE order_id IS\nNOT NULL'),
            references=(CompileSqlReference(SqlReferenceKind.REF, "orders"),),
            column_nullability_by_table={"orders": {"order_id": InferredNullability.NULLABLE}},
            column_types_by_table={"orders": {"order_id": "INTEGER"}},
            expected_columns=(
                InferredColumn(
                    name="order_id",
                    type="INT",
                    nullability=InferredNullability.NON_NULL,
                ),
            ),
            expected_lineage_columns=direct_orders_lineage("order_id"),
            expected_has_star=False,
        ),
        PolyglotAnalysisTestCase(
            description="refines a compact filtered outer join across a comment",
            query_sql=(
                'SELECT c.customer_id FROM __ref("orders") AS o '
                'LEFT JOIN __ref("customers") AS c '
                "ON o.order_id = c.customer_id "
                "WHERE c.customer_id IS /* required customer */ NOT NULL"
            ),
            references=(
                CompileSqlReference(SqlReferenceKind.REF, "orders"),
                CompileSqlReference(SqlReferenceKind.REF, "customers"),
            ),
            column_nullability_by_table={
                "orders": {"order_id": InferredNullability.NON_NULL},
                "customers": {"customer_id": InferredNullability.NON_NULL},
            },
            column_types_by_table={
                "orders": {"order_id": "INTEGER"},
                "customers": {"customer_id": "INTEGER"},
            },
            expected_columns=(
                InferredColumn(
                    name="customer_id",
                    type="INT",
                    nullability=InferredNullability.NON_NULL,
                ),
            ),
            expected_lineage_columns=(
                CompiledLineageColumnFact(
                    output_column="customer_id",
                    upstream_columns=(
                        CompiledLineageSourceFact(
                            resource_type=CompiledResourceType.MODEL,
                            resource_name="customers",
                            column_name="customer_id",
                        ),
                    ),
                    transform_kind=ColumnTransformKind.DIRECT,
                    confidence=ColumnLineageConfidence.HIGH,
                ),
            ),
            expected_has_star=False,
        ),
        PolyglotAnalysisTestCase(
            description="terminates direct lineage at a managed table function output",
            query_sql='SELECT order_id FROM __table_fn("customer_orders")(42)',
            references=(
                CompileSqlReference(
                    SqlReferenceKind.TABLE_FUNCTION,
                    "customer_orders",
                    call_argument_count=1,
                ),
            ),
            expected_columns=(InferredColumn(name="order_id"),),
            expected_lineage_columns=(
                CompiledLineageColumnFact(
                    output_column="order_id",
                    upstream_columns=(
                        CompiledLineageSourceFact(
                            resource_type=CompiledResourceType.TABLE_FN,
                            resource_name="customer_orders",
                            column_name="order_id",
                        ),
                    ),
                    transform_kind=ColumnTransformKind.DIRECT,
                    confidence=ColumnLineageConfidence.HIGH,
                ),
            ),
            expected_has_star=False,
        ),
        PolyglotAnalysisTestCase(
            description="preserves Snowflake custom cast names through combined analysis",
            query_sql="SELECT CAST(NULL AS VARIANT) AS value",
            references=(),
            expected_columns=(
                InferredColumn(
                    name="value", type="VARIANT", nullability=InferredNullability.NULLABLE
                ),
            ),
            expected_lineage_columns=(
                CompiledLineageColumnFact(
                    output_column="value",
                    upstream_columns=(),
                    transform_kind=ColumnTransformKind.CAST,
                    confidence=ColumnLineageConfidence.UNKNOWN,
                ),
            ),
            expected_has_star=False,
            inference_profile=ExpressionInferenceProfile(sql_analysis_dialect="snowflake"),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_ref_query_when_analyzing_columns_and_lineage_then_returns_compact_facts(
    test_case: PolyglotAnalysisTestCase,
) -> None:
    result: PolyglotAnalysisResult = analyze_columns_and_lineage_with_polyglot(
        query_sql=test_case.query_sql,
        references=test_case.references,
        column_nullability_by_table=test_case.column_nullability_by_table,
        column_types_by_table=test_case.column_types_by_table,
        inference_profile=test_case.inference_profile,
        allow_compact_analysis=True,
        recover_cte_facts=True,
    )

    assert result.analysis_succeeded
    assert result.columns == test_case.expected_columns
    assert result.lineage_columns == test_case.expected_lineage_columns
    assert result.has_star is test_case.expected_has_star


@pytest.mark.parametrize(
    "test_case",
    [
        PolyglotAnalysisTestCase(
            description="preserves fallback lineage for a commented qualified column",
            query_sql=(
                "SELECT orders.order_id,\n"
                "-- Current order status.\n"
                'orders.status FROM __ref("orders") AS orders'
            ),
            references=(CompileSqlReference(SqlReferenceKind.REF, "orders"),),
            expected_columns=(InferredColumn(name="order_id"), InferredColumn(name="status")),
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
                    confidence=ColumnLineageConfidence.HIGH,
                ),
                CompiledLineageColumnFact(
                    output_column="status",
                    upstream_columns=(
                        CompiledLineageSourceFact(
                            resource_type=CompiledResourceType.MODEL,
                            resource_name="orders",
                            column_name="status",
                        ),
                    ),
                    transform_kind=ColumnTransformKind.DIRECT,
                    confidence=ColumnLineageConfidence.HIGH,
                ),
            ),
            expected_has_star=False,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_annotated_projection_when_using_ast_fallback_then_lineage_is_preserved(
    test_case: PolyglotAnalysisTestCase,
) -> None:
    result: PolyglotAnalysisResult = analyze_columns_and_lineage_with_polyglot(
        query_sql=test_case.query_sql,
        references=test_case.references,
        allow_compact_analysis=False,
    )

    assert result.analysis_succeeded
    assert result.columns == test_case.expected_columns
    assert result.lineage_columns == test_case.expected_lineage_columns
    assert result.has_star is test_case.expected_has_star


@pytest.mark.parametrize(
    "test_case",
    [
        PolyglotAnalysisTestCase(
            description="uses compact query analysis before AST fallback",
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
                    confidence=ColumnLineageConfidence.HIGH,
                ),
            ),
            expected_has_star=False,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_compact_query_analysis_when_ast_parse_would_fail_then_returns_compact_facts(
    test_case: PolyglotAnalysisTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    polyglot_module: object | None = import_polyglot_sql()
    assert polyglot_module is not None

    def raise_parse_error(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise AssertionError("AST parse should not be called")

    monkeypatch.setattr(polyglot_module, "parse_one", raise_parse_error)

    result: PolyglotAnalysisResult = analyze_columns_and_lineage_with_polyglot(
        query_sql=test_case.query_sql,
        references=test_case.references,
        allow_compact_analysis=True,
    )

    assert result.analysis_succeeded
    assert result.columns == test_case.expected_columns
    assert result.lineage_columns == test_case.expected_lineage_columns
    assert result.has_star is test_case.expected_has_star


@pytest.mark.parametrize(
    "test_case",
    [
        PolyglotAnalysisTestCase(
            description="uses compact analysis for aggregate transforms",
            query_sql='SELECT COUNT(*) AS n, SUM(amount) AS total FROM __ref("orders")',
            references=(CompileSqlReference(SqlReferenceKind.REF, "orders"),),
            expected_columns=(
                InferredColumn(name="n", type="BIGINT", nullability=InferredNullability.NON_NULL),
                InferredColumn(name="total", type="DECIMAL"),
            ),
            expected_lineage_columns=(
                CompiledLineageColumnFact(
                    output_column="n",
                    upstream_columns=(),
                    transform_kind=ColumnTransformKind.AGGREGATION,
                    confidence=ColumnLineageConfidence.UNKNOWN,
                ),
                CompiledLineageColumnFact(
                    output_column="total",
                    upstream_columns=(
                        CompiledLineageSourceFact(
                            resource_type=CompiledResourceType.MODEL,
                            resource_name="orders",
                            column_name="amount",
                        ),
                    ),
                    transform_kind=ColumnTransformKind.AGGREGATION,
                    confidence=ColumnLineageConfidence.HIGH,
                ),
            ),
            expected_has_star=False,
        ),
        PolyglotAnalysisTestCase(
            description="uses compact analysis for expression transforms",
            query_sql='SELECT amount + tax AS total FROM __ref("orders")',
            references=(CompileSqlReference(SqlReferenceKind.REF, "orders"),),
            expected_columns=(InferredColumn(name="total"),),
            expected_lineage_columns=(
                CompiledLineageColumnFact(
                    output_column="total",
                    upstream_columns=(
                        CompiledLineageSourceFact(
                            resource_type=CompiledResourceType.MODEL,
                            resource_name="orders",
                            column_name="amount",
                        ),
                        CompiledLineageSourceFact(
                            resource_type=CompiledResourceType.MODEL,
                            resource_name="orders",
                            column_name="tax",
                        ),
                    ),
                    transform_kind=ColumnTransformKind.EXPRESSION,
                    confidence=ColumnLineageConfidence.HIGH,
                ),
            ),
            expected_has_star=False,
        ),
        PolyglotAnalysisTestCase(
            description="uses compact analysis for cte lineage",
            query_sql=(
                'WITH base AS (SELECT order_id FROM __ref("orders")) SELECT order_id FROM base'
            ),
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
                    confidence=ColumnLineageConfidence.HIGH,
                ),
            ),
            expected_has_star=False,
        ),
        PolyglotAnalysisTestCase(
            description="uses compact analysis for set operation branch lineage",
            query_sql=(
                'SELECT order_id FROM __ref("orders") UNION ALL SELECT return_id FROM __ref("returns")'
            ),
            references=(
                CompileSqlReference(SqlReferenceKind.REF, "orders"),
                CompileSqlReference(SqlReferenceKind.REF, "returns"),
            ),
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
                        CompiledLineageSourceFact(
                            resource_type=CompiledResourceType.MODEL,
                            resource_name="returns",
                            column_name="return_id",
                        ),
                    ),
                    transform_kind=ColumnTransformKind.DIRECT,
                    confidence=ColumnLineageConfidence.HIGH,
                ),
            ),
            expected_has_star=False,
        ),
        PolyglotAnalysisTestCase(
            description="uses compact analysis for qualified stars",
            query_sql=(
                'SELECT o.* FROM __ref("orders") o JOIN __ref("customers") c ON o.customer_id = c.id'
            ),
            references=(
                CompileSqlReference(SqlReferenceKind.REF, "orders"),
                CompileSqlReference(SqlReferenceKind.REF, "customers"),
            ),
            expected_columns=(),
            expected_lineage_columns=(),
            expected_has_star=True,
        ),
        PolyglotAnalysisTestCase(
            description="uses compact schema metadata for unqualified column resolution",
            query_sql=(
                'SELECT amount FROM __ref("orders") o JOIN __ref("customers") c ON o.customer_id = c.id'
            ),
            references=(
                CompileSqlReference(SqlReferenceKind.REF, "orders"),
                CompileSqlReference(SqlReferenceKind.REF, "customers"),
            ),
            column_nullability_by_table={
                "orders": {
                    "amount": InferredNullability.UNKNOWN,
                    "customer_id": InferredNullability.UNKNOWN,
                },
                "customers": {"id": InferredNullability.UNKNOWN},
            },
            expected_columns=(InferredColumn(name="amount"),),
            expected_lineage_columns=(
                CompiledLineageColumnFact(
                    output_column="amount",
                    upstream_columns=(
                        CompiledLineageSourceFact(
                            resource_type=CompiledResourceType.MODEL,
                            resource_name="orders",
                            column_name="amount",
                        ),
                    ),
                    transform_kind=ColumnTransformKind.DIRECT,
                    confidence=ColumnLineageConfidence.HIGH,
                ),
            ),
            expected_has_star=False,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_supported_compact_query_when_ast_parse_would_fail_then_returns_analysis_facts(
    test_case: PolyglotAnalysisTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    polyglot_module: object | None = import_polyglot_sql()
    assert polyglot_module is not None

    def raise_parse_error(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise AssertionError("AST parse should not be called")

    monkeypatch.setattr(polyglot_module, "parse_one", raise_parse_error)

    result: PolyglotAnalysisResult = analyze_columns_and_lineage_with_polyglot(
        query_sql=test_case.query_sql,
        references=test_case.references,
        column_nullability_by_table=test_case.column_nullability_by_table,
        allow_compact_analysis=True,
    )

    assert result.analysis_succeeded
    assert result.columns == test_case.expected_columns
    assert result.lineage_columns == test_case.expected_lineage_columns
    assert result.has_star is test_case.expected_has_star


@pytest.mark.parametrize(
    "test_case",
    [
        PolyglotAnalysisTestCase(
            description="preserves a cast type through direct cte passthroughs",
            query_sql=(
                "WITH transformed AS ("
                'SELECT CAST(amount AS INTEGER) AS amount FROM __ref("orders")'
                "), final AS ("
                "SELECT amount FROM transformed"
                ") SELECT amount FROM final"
            ),
            references=(CompileSqlReference(SqlReferenceKind.REF, "orders"),),
            column_nullability_by_table={"orders": {"amount": InferredNullability.NON_NULL}},
            column_types_by_table={"orders": {"amount": "VARCHAR"}},
            expected_columns=(
                InferredColumn(
                    name="amount",
                    type="INT",
                    nullability=InferredNullability.NON_NULL,
                ),
            ),
            expected_lineage_columns=direct_orders_lineage("amount"),
            expected_has_star=False,
        ),
        PolyglotAnalysisTestCase(
            description="does not reuse a source type through a transformed cte",
            query_sql=(
                "WITH transformed AS ("
                "SELECT amount || '0' AS amount FROM __ref(\"orders\")"
                "), final AS ("
                "SELECT amount FROM transformed"
                ") SELECT amount FROM final"
            ),
            references=(CompileSqlReference(SqlReferenceKind.REF, "orders"),),
            column_nullability_by_table={"orders": {"amount": InferredNullability.UNKNOWN}},
            column_types_by_table={"orders": {"amount": "INTEGER"}},
            expected_columns=(InferredColumn(name="amount"),),
            expected_lineage_columns=direct_orders_lineage("amount"),
            expected_has_star=False,
        ),
        PolyglotAnalysisTestCase(
            description="preserves only matching recursive by-name cte union types",
            query_sql=(
                "WITH current_orders AS ("
                "SELECT CAST(amount AS INTEGER) AS amount, "
                'CAST(status AS VARCHAR) AS status FROM __ref("orders")'
                "), archived_orders AS ("
                "SELECT CAST(amount AS FLOAT) AS amount, "
                'CAST(status AS VARCHAR) AS status FROM __ref("orders")'
                "), imported_orders AS ("
                "SELECT CAST(amount AS INTEGER) AS amount, "
                'CAST(status AS VARCHAR) AS status FROM __ref("orders")'
                "), combined AS ("
                "SELECT amount, status FROM current_orders "
                "-- include archived rows\n"
                "UNION ALL BY NAME SELECT amount, status FROM archived_orders "
                "-- include imported rows\n"
                "UNION ALL BY NAME SELECT amount, status FROM imported_orders"
                "), final AS ("
                "SELECT amount, status FROM combined"
                ") SELECT amount, status FROM final"
            ),
            references=(
                CompileSqlReference(SqlReferenceKind.REF, "orders"),
                CompileSqlReference(SqlReferenceKind.REF, "orders"),
                CompileSqlReference(SqlReferenceKind.REF, "orders"),
            ),
            column_nullability_by_table={
                "orders": {
                    "amount": InferredNullability.UNKNOWN,
                    "status": InferredNullability.UNKNOWN,
                }
            },
            column_types_by_table={"orders": {"amount": "VARCHAR", "status": "VARCHAR"}},
            expected_columns=(
                InferredColumn(name="amount"),
                InferredColumn(name="status", type="TEXT"),
            ),
            expected_lineage_columns=direct_orders_lineage("amount", "status"),
            expected_has_star=False,
        ),
        PolyglotAnalysisTestCase(
            description="preserves matching positional cte union types",
            query_sql=(
                "WITH combined AS ("
                "SELECT CAST(amount AS INTEGER) AS amount, "
                "CAST(status AS VARCHAR) AS status, "
                'CAST(status AS VARCHAR) AS nullable_status FROM __ref("orders") '
                "UNION ALL SELECT amount, status, "
                'NULL AS nullable_status FROM __ref("orders")'
                "), final AS ("
                "SELECT amount, status, nullable_status FROM combined"
                ") SELECT amount, status, nullable_status FROM final"
            ),
            references=(
                CompileSqlReference(SqlReferenceKind.REF, "orders"),
                CompileSqlReference(SqlReferenceKind.REF, "orders"),
            ),
            column_nullability_by_table={
                "orders": {
                    "amount": InferredNullability.UNKNOWN,
                    "status": InferredNullability.UNKNOWN,
                }
            },
            column_types_by_table={
                "orders": {
                    "amount": "NUMBER(38,0)",
                    "status": "VARCHAR(16777216)",
                }
            },
            inference_profile=ExpressionInferenceProfile(sql_analysis_dialect="snowflake"),
            expected_columns=(
                InferredColumn(name="amount", type="INT"),
                InferredColumn(name="status", type="TEXT"),
                InferredColumn(name="nullable_status", type="TEXT"),
            ),
            expected_lineage_columns=direct_orders_lineage("amount", "status")
            + (
                CompiledLineageColumnFact(
                    output_column="nullable_status",
                    upstream_columns=(
                        CompiledLineageSourceFact(
                            resource_type=CompiledResourceType.MODEL,
                            resource_name="orders",
                            column_name="status",
                        ),
                    ),
                    transform_kind=ColumnTransformKind.DIRECT,
                    confidence=ColumnLineageConfidence.HIGH,
                ),
            ),
            expected_has_star=False,
        ),
        PolyglotAnalysisTestCase(
            description="preserves by-name wildcard cte union types",
            query_sql=(
                "WITH typed AS ("
                'SELECT CAST(amount AS INTEGER) AS amount FROM __ref("orders")'
                "), combined AS ("
                "SELECT * FROM typed UNION ALL BY NAME SELECT * FROM typed"
                "), final AS ("
                "SELECT amount FROM combined"
                ") SELECT amount FROM final"
            ),
            references=(CompileSqlReference(SqlReferenceKind.REF, "orders"),),
            column_nullability_by_table={"orders": {"amount": InferredNullability.UNKNOWN}},
            column_types_by_table={"orders": {"amount": "VARCHAR"}},
            expected_columns=(InferredColumn(name="amount", type="INT"),),
            expected_lineage_columns=direct_orders_lineage("amount"),
            expected_has_star=False,
        ),
        PolyglotAnalysisTestCase(
            description="declines cte column-list type recovery",
            query_sql=(
                "WITH transformed(amount, status) AS ("
                "SELECT CAST(amount AS VARCHAR) AS status, "
                'CAST(amount AS INTEGER) AS amount FROM __ref("orders")'
                "), final AS ("
                "SELECT amount FROM transformed"
                ") SELECT amount FROM final"
            ),
            references=(CompileSqlReference(SqlReferenceKind.REF, "orders"),),
            column_nullability_by_table={"orders": {"amount": InferredNullability.UNKNOWN}},
            column_types_by_table={"orders": {"amount": "VARCHAR"}},
            expected_columns=(InferredColumn(name="amount"),),
            expected_lineage_columns=direct_orders_lineage("amount"),
            expected_has_star=False,
        ),
        PolyglotAnalysisTestCase(
            description="declines sparse positional union type recovery",
            query_sql=(
                "WITH combined AS ("
                "SELECT CAST(amount AS INTEGER) AS amount, amount || 'x' AS status "
                'FROM __ref("orders") UNION ALL '
                "SELECT amount || 'x' AS status, CAST(amount AS INTEGER) AS amount "
                'FROM __ref("orders")'
                "), final AS ("
                "SELECT amount FROM combined"
                ") SELECT amount FROM final"
            ),
            references=(
                CompileSqlReference(SqlReferenceKind.REF, "orders"),
                CompileSqlReference(SqlReferenceKind.REF, "orders"),
            ),
            column_nullability_by_table={"orders": {"amount": InferredNullability.UNKNOWN}},
            column_types_by_table={"orders": {"amount": "VARCHAR"}},
            expected_columns=(InferredColumn(name="amount"),),
            expected_lineage_columns=direct_orders_lineage("amount"),
            expected_has_star=False,
        ),
        PolyglotAnalysisTestCase(
            description="preserves renamed star lineage without recovering type",
            query_sql=(
                "WITH typed AS ("
                "SELECT CAST(amount AS INTEGER) AS amount, "
                'CAST(amount AS VARCHAR) AS status FROM __ref("orders")'
                "), renamed AS ("
                "SELECT * RENAME (amount AS status, status AS amount) FROM typed"
                "), final AS ("
                "SELECT amount FROM renamed"
                ") SELECT amount FROM final"
            ),
            references=(CompileSqlReference(SqlReferenceKind.REF, "orders"),),
            column_nullability_by_table={"orders": {"amount": InferredNullability.UNKNOWN}},
            column_types_by_table={"orders": {"amount": "VARCHAR"}},
            inference_profile=ExpressionInferenceProfile(sql_analysis_dialect="snowflake"),
            expected_columns=(InferredColumn(name="amount"),),
            expected_lineage_columns=direct_orders_lineage("amount"),
            expected_has_star=False,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_cte_chain_when_analyzing_direct_passthrough_then_type_is_conservative(
    test_case: PolyglotAnalysisTestCase,
) -> None:
    result: PolyglotAnalysisResult = analyze_columns_and_lineage_with_polyglot(
        query_sql=test_case.query_sql,
        references=test_case.references,
        column_nullability_by_table=test_case.column_nullability_by_table,
        column_types_by_table=test_case.column_types_by_table,
        inference_profile=test_case.inference_profile,
        allow_compact_analysis=True,
        recover_cte_facts=True,
    )

    assert result.analysis_succeeded
    assert result.columns == test_case.expected_columns
    assert result.lineage_columns == test_case.expected_lineage_columns
    assert result.has_star is test_case.expected_has_star


@pytest.mark.parametrize(
    "test_case",
    [
        PolyglotAnalysisTestCase(
            description="preserves safe expression types without over-inferring overloads",
            query_sql=(
                "WITH transformed AS ("
                "SELECT "
                "'web' AS source_name, "
                "TRUE AS active, "
                "order_id IN (1, 2) AS selected, "
                "first_name || last_name AS full_name, "
                "COALESCE(status, CAST(NULL AS VARCHAR)) AS status, "
                "IFF(active, status, NULL) AS maybe_status, "
                "CASE WHEN active THEN status ELSE NULL END AS case_status, "
                "NULLIF(status, '') AS clean_status, "
                "MIN(created_at) OVER (PARTITION BY order_id) AS first_created_at, "
                "to_date, "
                "payload || payload AS merged_payload, "
                "SUBSTRING(payload, 1, 2) AS sliced_payload "
                'FROM __ref("orders")'
                "), final AS ("
                "SELECT source_name, active, selected, full_name, status, maybe_status, "
                "case_status, clean_status, first_created_at, to_date, merged_payload, "
                "sliced_payload FROM transformed"
                ") SELECT source_name, active, selected, full_name, status, maybe_status, "
                "case_status, clean_status, first_created_at, to_date, merged_payload, "
                "sliced_payload FROM final"
            ),
            references=(CompileSqlReference(SqlReferenceKind.REF, "orders"),),
            column_nullability_by_table={
                "orders": {
                    "order_id": InferredNullability.NON_NULL,
                    "first_name": InferredNullability.UNKNOWN,
                    "last_name": InferredNullability.UNKNOWN,
                    "status": InferredNullability.UNKNOWN,
                    "active": InferredNullability.UNKNOWN,
                    "created_at": InferredNullability.UNKNOWN,
                    "to_date": InferredNullability.UNKNOWN,
                    "payload": InferredNullability.UNKNOWN,
                }
            },
            column_types_by_table={
                "orders": {
                    "order_id": "NUMBER(38,0)",
                    "first_name": "VARCHAR(16777216)",
                    "last_name": "VARCHAR(16777216)",
                    "status": "VARCHAR(16777216)",
                    "active": "BOOLEAN",
                    "created_at": "TIMESTAMP_NTZ",
                    "to_date": "INTEGER",
                    "payload": "BINARY",
                }
            },
            inference_profile=ExpressionInferenceProfile(
                sql_analysis_dialect="snowflake",
                function_return_types={"TO_DATE": "DATE"},
            ),
            expected_columns=(
                InferredColumn(
                    name="source_name",
                    nullability=InferredNullability.NON_NULL,
                ),
                InferredColumn(name="active", type="BOOLEAN"),
                InferredColumn(name="selected", type="BOOLEAN"),
                InferredColumn(name="full_name", type="TEXT"),
                InferredColumn(name="status", type="VARCHAR(16777216)"),
                InferredColumn(name="maybe_status", type="VARCHAR(16777216)"),
                InferredColumn(name="case_status", type="VARCHAR(16777216)"),
                InferredColumn(name="clean_status", type="VARCHAR(16777216)"),
                InferredColumn(name="first_created_at", type="TIMESTAMP_NTZ"),
                InferredColumn(name="to_date", type="INTEGER"),
                InferredColumn(name="merged_payload"),
                InferredColumn(name="sliced_payload", type="BINARY"),
            ),
            expected_lineage_columns=(),
            expected_has_star=False,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_typed_cte_expressions_when_recovering_facts_then_safe_result_types_are_preserved(
    test_case: PolyglotAnalysisTestCase,
) -> None:
    result: PolyglotAnalysisResult = analyze_columns_and_lineage_with_polyglot(
        query_sql=test_case.query_sql,
        references=test_case.references,
        column_nullability_by_table=test_case.column_nullability_by_table,
        column_types_by_table=test_case.column_types_by_table,
        inference_profile=test_case.inference_profile,
        allow_compact_analysis=True,
        recover_cte_facts=True,
    )

    assert result.columns == test_case.expected_columns


@pytest.mark.parametrize(
    "test_case",
    [
        PolyglotAnalysisTestCase(
            description="keeps star lineage conservative on fast path",
            query_sql='SELECT * FROM __ref("orders")',
            references=(CompileSqlReference(SqlReferenceKind.REF, "orders"),),
            column_nullability_by_table={
                "orders": {
                    "order_id": InferredNullability.NON_NULL,
                    "status": InferredNullability.NULLABLE,
                }
            },
            expected_columns=(),
            expected_lineage_columns=(),
            expected_has_star=True,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_star_projection_when_compact_analysis_disabled_then_marks_star_without_expansion(
    test_case: PolyglotAnalysisTestCase,
) -> None:
    result: PolyglotAnalysisResult = analyze_columns_and_lineage_with_polyglot(
        query_sql=test_case.query_sql,
        references=test_case.references,
        column_nullability_by_table=test_case.column_nullability_by_table,
    )

    assert result.analysis_succeeded
    assert result.columns == test_case.expected_columns
    assert result.lineage_columns == test_case.expected_lineage_columns
    assert result.has_star is test_case.expected_has_star


@pytest.mark.parametrize(
    "test_case",
    [
        PolyglotAnalysisTestCase(
            description="expands star lineage on rich compact path",
            query_sql='SELECT * FROM __ref("orders")',
            references=(CompileSqlReference(SqlReferenceKind.REF, "orders"),),
            column_nullability_by_table={
                "orders": {
                    "order_id": InferredNullability.NON_NULL,
                    "status": InferredNullability.NULLABLE,
                }
            },
            expected_columns=(
                InferredColumn(name="order_id", nullability=InferredNullability.NON_NULL),
                InferredColumn(name="status", nullability=InferredNullability.NULLABLE),
            ),
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
                    confidence=ColumnLineageConfidence.HIGH,
                ),
                CompiledLineageColumnFact(
                    output_column="status",
                    upstream_columns=(
                        CompiledLineageSourceFact(
                            resource_type=CompiledResourceType.MODEL,
                            resource_name="orders",
                            column_name="status",
                        ),
                    ),
                    transform_kind=ColumnTransformKind.DIRECT,
                    confidence=ColumnLineageConfidence.HIGH,
                ),
            ),
            expected_has_star=True,
        ),
        PolyglotAnalysisTestCase(
            description="expands declared table function output columns on rich compact path",
            query_sql='SELECT * FROM __table_fn("customer_orders")(42)',
            references=(
                CompileSqlReference(
                    SqlReferenceKind.TABLE_FUNCTION,
                    "customer_orders",
                    call_argument_count=1,
                ),
            ),
            column_nullability_by_table={
                "__sqlbuild_table_function_customer_orders": {
                    "status": InferredNullability.UNKNOWN,
                    "order_id": InferredNullability.UNKNOWN,
                }
            },
            column_types_by_table={
                "__sqlbuild_table_function_customer_orders": {
                    "status": "VARCHAR",
                    "order_id": "BIGINT",
                }
            },
            expected_columns=(
                InferredColumn(name="status", type="VARCHAR"),
                InferredColumn(name="order_id", type="BIGINT"),
            ),
            expected_lineage_columns=(
                CompiledLineageColumnFact(
                    output_column="status",
                    upstream_columns=(
                        CompiledLineageSourceFact(
                            resource_type=CompiledResourceType.TABLE_FN,
                            resource_name="customer_orders",
                            column_name="status",
                        ),
                    ),
                    transform_kind=ColumnTransformKind.DIRECT,
                    confidence=ColumnLineageConfidence.HIGH,
                ),
                CompiledLineageColumnFact(
                    output_column="order_id",
                    upstream_columns=(
                        CompiledLineageSourceFact(
                            resource_type=CompiledResourceType.TABLE_FN,
                            resource_name="customer_orders",
                            column_name="order_id",
                        ),
                    ),
                    transform_kind=ColumnTransformKind.DIRECT,
                    confidence=ColumnLineageConfidence.HIGH,
                ),
            ),
            expected_has_star=True,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_star_projection_when_compact_analysis_enabled_then_expands_schema_lineage(
    test_case: PolyglotAnalysisTestCase,
) -> None:
    result: PolyglotAnalysisResult = analyze_columns_and_lineage_with_polyglot(
        query_sql=test_case.query_sql,
        references=test_case.references,
        column_nullability_by_table=test_case.column_nullability_by_table,
        column_types_by_table=test_case.column_types_by_table,
        allow_compact_analysis=True,
    )

    assert result.analysis_succeeded
    assert result.columns == test_case.expected_columns
    assert result.lineage_columns == test_case.expected_lineage_columns
    assert result.has_star is test_case.expected_has_star


@pytest.mark.parametrize(
    "test_case",
    [
        PolyglotAnalysisTestCase(
            description="matches AST fallback for unqualified single ref",
            query_sql='SELECT order_id FROM __ref("orders")',
            references=(CompileSqlReference(SqlReferenceKind.REF, "orders"),),
            expected_columns=(),
            expected_lineage_columns=(),
            expected_has_star=False,
        ),
        PolyglotAnalysisTestCase(
            description="matches AST fallback for qualified join refs",
            query_sql=(
                'SELECT o.order_id, c.name FROM __ref("orders") o '
                'JOIN __ref("customers") c ON o.customer_id = c.customer_id'
            ),
            references=(
                CompileSqlReference(SqlReferenceKind.REF, "orders"),
                CompileSqlReference(SqlReferenceKind.REF, "customers"),
            ),
            expected_columns=(),
            expected_lineage_columns=(),
            expected_has_star=False,
        ),
        PolyglotAnalysisTestCase(
            description="matches AST fallback for source refs",
            query_sql='SELECT payment_id FROM __source("stripe__payments")',
            references=(CompileSqlReference(SqlReferenceKind.SOURCE, "stripe__payments"),),
            expected_columns=(),
            expected_lineage_columns=(),
            expected_has_star=False,
        ),
        PolyglotAnalysisTestCase(
            description="matches AST fallback for seed refs",
            query_sql='SELECT lookup_id FROM __seed("order_statuses")',
            references=(CompileSqlReference(SqlReferenceKind.SEED, "order_statuses"),),
            expected_columns=(),
            expected_lineage_columns=(),
            expected_has_star=False,
        ),
        PolyglotAnalysisTestCase(
            description="matches AST fallback for casted ref column",
            query_sql='SELECT CAST(order_id AS BIGINT) AS order_id FROM __ref("orders")',
            references=(CompileSqlReference(SqlReferenceKind.REF, "orders"),),
            expected_columns=(),
            expected_lineage_columns=(),
            expected_has_star=False,
        ),
        PolyglotAnalysisTestCase(
            description="matches AST fallback for arithmetic expression fallback",
            query_sql='SELECT amount + tax AS total FROM __ref("orders")',
            references=(CompileSqlReference(SqlReferenceKind.REF, "orders"),),
            expected_columns=(),
            expected_lineage_columns=(),
            expected_has_star=False,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_compact_query_analysis_safe_shape_when_analyzing_then_matches_ast_facts(
    test_case: PolyglotAnalysisTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    compact_result: PolyglotAnalysisResult = analyze_columns_and_lineage_with_polyglot(
        query_sql=test_case.query_sql,
        references=test_case.references,
        allow_compact_analysis=True,
    )
    assert compact_result.analysis_succeeded
    assert compact_result.has_star is test_case.expected_has_star

    polyglot_module: object | None = import_polyglot_sql()
    assert polyglot_module is not None

    def raise_compact_error(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise ParseError("compact analysis disabled")

    monkeypatch.setattr(polyglot_module, "analyze_query", raise_compact_error)
    fallback_result: PolyglotAnalysisResult = analyze_columns_and_lineage_with_polyglot(
        query_sql=test_case.query_sql,
        references=test_case.references,
        allow_compact_analysis=True,
    )

    assert fallback_result.analysis_succeeded
    assert compact_result.columns == fallback_result.columns
    assert compact_result.has_star == fallback_result.has_star
    compact_lineage_columns: tuple[CompiledLineageColumnFact, ...] = compact_result.lineage_columns
    fallback_lineage_columns: tuple[CompiledLineageColumnFact, ...] = (
        fallback_result.lineage_columns
    )
    assert len(compact_lineage_columns) == len(fallback_lineage_columns)
    for compact_fact, fallback_fact in zip(
        compact_lineage_columns,
        fallback_lineage_columns,
        strict=True,
    ):
        assert compact_fact.output_column == fallback_fact.output_column
        assert compact_fact.upstream_columns == fallback_fact.upstream_columns
        assert compact_fact.transform_kind == fallback_fact.transform_kind


@pytest.mark.parametrize(
    "test_case",
    [
        UnexpectedAnalysisFailureTestCase(
            description="unexpected native integration failure",
            expected_error="unexpected native integration failure",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_unexpected_polyglot_failure_when_analyzing_then_failure_is_not_silenced(
    test_case: UnexpectedAnalysisFailureTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    polyglot_module: object = import_polyglot_sql()

    def raise_unexpected_failure(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise RuntimeError(test_case.expected_error)

    monkeypatch.setattr(polyglot_module, "analyze_query", raise_unexpected_failure)

    with pytest.raises(RuntimeError, match=test_case.expected_error):
        analyze_columns_and_lineage_with_polyglot(
            query_sql='SELECT id FROM __ref("orders")',
            references=(CompileSqlReference(SqlReferenceKind.REF, "orders"),),
            allow_compact_analysis=True,
        )


@pytest.mark.parametrize(
    "test_case",
    [
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
    ],
    ids=lambda case: case.description,
)
def test_given_sql_with_placeholders_when_substituting_then_returns_expected(
    test_case: SubstitutePlaceholderDefaultsTestCase,
) -> None:
    result: str = substitute_placeholder_defaults(
        query_sql=test_case.query_sql, placeholders=test_case.placeholders
    )

    assert result == test_case.expected_sql
