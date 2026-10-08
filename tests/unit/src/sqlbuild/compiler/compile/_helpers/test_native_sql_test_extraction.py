from __future__ import annotations

import pytest

from sqlbuild.adapters.bigquery.classes.bigquery_adapter import BigQueryAdapter
from sqlbuild.adapters.databricks.classes.databricks_adapter import DatabricksAdapter
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.adapters.postgres.classes.postgres_adapter import PostgresAdapter
from sqlbuild.adapters.snowflake.classes.snowflake_adapter import SnowflakeAdapter
from sqlbuild.compiler.compile._helpers.sql_tests.core import (
    extract_assertion_target_model_names,
)
from sqlbuild.compiler.compile._helpers.sql_tests.native import (
    extract_expanded_sql_tests,
    extract_unexpanded_sql_test,
)
from sqlbuild.compiler.compile.models import CompileModelSqlTestCtes, CompileSqlTestCtes
from sqlbuild.compiler.compile.types import SqlTestMode
from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax
from tests.unit.src.sqlbuild.compiler.compile._helpers._test_types import (
    DialectCteScanTestCase,
    ExpectedMessageTestCase,
    NativeSqlTestExtractionParityTestCase,
)

_GENERIC_SQL_SYNTAX: SqlLexicalSyntax = SqlLexicalSyntax()


@pytest.mark.parametrize(
    "test_case",
    (
        NativeSqlTestExtractionParityTestCase(
            description="model roles retain authored ordering and independent checks",
            sql=(
                "WITH helper AS (SELECT 1 AS order_id), "
                "__source__raw_orders AS (SELECT order_id FROM helper), "
                "__macro__status AS (SELECT '''created'''), "
                "__expected__orders AS (SELECT order_id FROM helper), "
                "__assert__positive AS (SELECT order_id FROM helper WHERE order_id < 0) "
                "SELECT 1"
            ),
            mode=SqlTestMode.MODEL,
        ),
        NativeSqlTestExtractionParityTestCase(
            description="macro direct logic retains helper actual and expected payloads",
            sql=(
                "WITH input AS (SELECT 'created' AS status), "
                "__macro_actual__ AS (SELECT @normalize_status(status) AS status FROM input), "
                "__macro_expected__ AS (SELECT 'created' AS status) SELECT 1"
            ),
            mode=SqlTestMode.MACRO,
        ),
        NativeSqlTestExtractionParityTestCase(
            description="udf direct logic retains helper actual and expected payloads",
            sql=(
                "WITH input AS (SELECT 1 AS value), "
                '__udf_actual__ AS (SELECT __udf("increment")(value) AS value FROM input), '
                "__udf_expected__ AS (SELECT 2 AS value) SELECT 1"
            ),
            mode=SqlTestMode.UDF,
        ),
        NativeSqlTestExtractionParityTestCase(
            description="table function direct logic retains actual and expected payloads",
            sql=(
                "__table_fn_actual__ AS (SELECT order_id FROM "
                '__table_fn("customer_orders")(1)), '
                "__table_fn_expected__ AS (SELECT 1 AS order_id) SELECT 1"
            ).join(("WITH ", "")),
            mode=SqlTestMode.TABLE_FN,
        ),
        NativeSqlTestExtractionParityTestCase(
            description="expected projection before where without from is accepted",
            sql=(
                "WITH __source__raw_orders AS (SELECT 1 AS id), "
                "__expected__orders AS ("
                "SELECT CAST(NULL AS INTEGER) AS id WHERE 1 = 0"
                ") SELECT 1"
            ),
            mode=SqlTestMode.MODEL,
        ),
        NativeSqlTestExtractionParityTestCase(
            description="qualified expected projection uses the column name",
            sql=(
                "WITH __source__raw_orders AS (SELECT 1 AS id), "
                "sample AS (SELECT 1 AS id), "
                "__expected__orders AS (SELECT sample.id FROM sample) SELECT 1"
            ),
            mode=SqlTestMode.MODEL,
        ),
        NativeSqlTestExtractionParityTestCase(
            description="clause-like qualified column uses its explicit alias",
            sql=(
                "WITH __source__raw_orders AS (SELECT 1 AS id), "
                "sample AS (SELECT 1 AS limit), "
                "__expected__orders AS (SELECT sample.limit AS id FROM sample) SELECT 1"
            ),
            mode=SqlTestMode.MODEL,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_macro_free_sql_tests_when_extracting_before_and_after_expansion_then_payloads_match(
    test_case: NativeSqlTestExtractionParityTestCase,
) -> None:
    expanded: tuple[CompileSqlTestCtes, ...] = extract_expanded_sql_tests(
        tests=((test_case.sql, "tests/unit/example.sql", test_case.mode),),
        syntax=_GENERIC_SQL_SYNTAX,
    )
    unexpanded: tuple[CompileSqlTestCtes, bool] = extract_unexpanded_sql_test(
        sql=test_case.sql,
        file_label="tests/unit/example.sql",
        mode=test_case.mode,
        syntax=_GENERIC_SQL_SYNTAX,
    )

    assert (expanded == (unexpanded[0],), unexpanded[1]) == (test_case.expected_matches, False)


@pytest.mark.parametrize(
    "test_case",
    [
        ExpectedMessageTestCase(
            description="a check reading an expected CTE through a helper",
            value=(
                "WITH __source__raw_orders AS (SELECT 1 AS order_id), "
                "__expected__orders AS (SELECT 1 AS order_id), "
                "helper AS (SELECT order_id FROM __expected__orders), "
                "__assert__same AS (SELECT order_id FROM helper) SELECT 1"
            ),
            expected_message=(
                "SQL test 'tests/unit/example.sql' check CTE '__assert__same' must not depend on "
                "'__expected__orders' through 'helper'; expected results and assertions must be "
                "independent"
            ),
        ),
        ExpectedMessageTestCase(
            description="a check joining an expected CTE in a comma-separated FROM",
            value=(
                "WITH __source__orders AS (SELECT 1 AS id), "
                "__expected__orders AS (SELECT 1 AS id), "
                "__assert__valid AS ("
                "SELECT expected.id FROM __source__orders source, __expected__orders expected"
                ") SELECT 1"
            ),
            expected_message=(
                "SQL test 'tests/unit/example.sql' check CTE '__assert__valid' must not depend on "
                "'__expected__orders'; expected results and assertions must be independent"
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_cross_check_dependency_when_extracting_then_independence_error_is_raised(
    test_case: ExpectedMessageTestCase,
) -> None:
    with pytest.raises(ValueError) as native_error:
        extract_expanded_sql_tests(
            tests=((test_case.value, "tests/unit/example.sql", SqlTestMode.MODEL),),
            syntax=_GENERIC_SQL_SYNTAX,
        )

    assert str(native_error.value) == test_case.expected_message


@pytest.mark.parametrize(
    "test_case",
    [
        DialectCteScanTestCase(
            description="snowflake backslash-escaped quote before a marker",
            syntax=SnowflakeAdapter.sql_lexical_syntax,
            sql=(
                "WITH\n"
                "__ref__stg_orders AS (SELECT 'O\\'Brien), (' AS customer_name),\n"
                "__assert__named AS (\n"
                "  SELECT 'O\\'Brien' AS customer_name, * FROM __ref(\"order_totals\")\n"
                ")\n"
                "SELECT 1"
            ),
            expected_cte_names=("__ref__stg_orders", "__assert__named"),
            expected_assertion_targets=("order_totals",),
        ),
        DialectCteScanTestCase(
            description="bigquery hash comment and triple quotes around markers",
            syntax=BigQueryAdapter.sql_lexical_syntax,
            sql=(
                "WITH\n"
                "__ref__stg_orders AS (SELECT '''it's ), (''' AS note), # ), (\n"
                "__assert__named AS (\n"
                '  SELECT * FROM __ref("order_totals") # __ref("ignored")\n'
                ")\n"
                "SELECT 1"
            ),
            expected_cte_names=("__ref__stg_orders", "__assert__named"),
            expected_assertion_targets=("order_totals",),
        ),
        DialectCteScanTestCase(
            description="databricks backslash-escaped quote before a marker",
            syntax=DatabricksAdapter.sql_lexical_syntax,
            sql=(
                "WITH\n"
                "__ref__stg_orders AS (SELECT 'O\\'Brien), (' AS customer_name),\n"
                "__assert__named AS (\n"
                "  SELECT 'O\\'Brien' AS customer_name, * FROM __ref(\"order_totals\")\n"
                ")\n"
                "SELECT 1"
            ),
            expected_cte_names=("__ref__stg_orders", "__assert__named"),
            expected_assertion_targets=("order_totals",),
        ),
        DialectCteScanTestCase(
            description="duckdb escape string and nested comment before a marker",
            syntax=DuckDbAdapter.sql_lexical_syntax,
            sql=(
                "WITH\n"
                "__ref__stg_orders AS (SELECT E'O\\'Brien), (' AS customer_name),\n"
                "/* outer /* inner */ ), ( */\n"
                "__assert__named AS (\n"
                "  SELECT E'O\\'Brien' AS customer_name, * FROM __ref(\"order_totals\")\n"
                ")\n"
                "SELECT 1"
            ),
            expected_cte_names=("__ref__stg_orders", "__assert__named"),
            expected_assertion_targets=("order_totals",),
        ),
        DialectCteScanTestCase(
            description="postgres escape string before a marker",
            syntax=PostgresAdapter.sql_lexical_syntax,
            sql=(
                "WITH\n"
                "__ref__stg_orders AS (SELECT E'O\\'Brien), (' AS customer_name),\n"
                "__assert__named AS (\n"
                "  SELECT E'O\\'Brien' AS customer_name, * FROM __ref(\"order_totals\")\n"
                ")\n"
                "SELECT 1"
            ),
            expected_cte_names=("__ref__stg_orders", "__assert__named"),
            expected_assertion_targets=("order_totals",),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_dialect_sql_test_when_batch_extracting_then_follows_dialect_lexical_rules(
    test_case: DialectCteScanTestCase,
) -> None:
    extracted: tuple[CompileSqlTestCtes, ...] = extract_expanded_sql_tests(
        tests=(
            (test_case.sql, "tests/unit/orders.sql", SqlTestMode.MODEL),
            (
                "WITH __ref__a AS (SELECT 1 AS id), __expected__b AS (SELECT 1 AS id) SELECT 1",
                "tests/unit/plain.sql",
                SqlTestMode.MODEL,
            ),
        ),
        syntax=test_case.syntax,
    )

    payload: object = extracted[0].payload
    assert isinstance(payload, CompileModelSqlTestCtes)
    assert (
        tuple(cte.name for cte in (*payload.authored_ctes, *payload.assertion_ctes))
        == test_case.expected_cte_names
    )
    assert (
        extract_assertion_target_model_names(
            assertion_sql=tuple(cte.sql_body for cte in payload.assertion_ctes),
            syntax=test_case.syntax,
        )
        == test_case.expected_assertion_targets
    )
    assert isinstance(extracted[1].payload, CompileModelSqlTestCtes)
    assert extracted[1].payload.expected_model_names == ("b",)


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
