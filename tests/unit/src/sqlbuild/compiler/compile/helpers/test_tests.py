from __future__ import annotations

import pytest

from sqlbuild.compiler.compile.helpers.tests import CompileSqlTestCtes, extract_sql_test_ctes
from tests.unit.src.sqlbuild.compiler.compile.helpers._test_types import (
    ExtractSqlTestCtesErrorTestCase,
    ExtractSqlTestCtesTestCase,
)

TEST_CASES: list[ExtractSqlTestCtesTestCase] = [
    ExtractSqlTestCtesTestCase(
        description="extracts seed mocks from seed-prefixed ctes",
        sql="""
        WITH
        __seed__country_codes AS (SELECT 'US' AS country_code),
        __expected__orders AS (SELECT 'US' AS country_code)
        SELECT 1
        """.strip(),
        expected_authored_cte_names=("__seed__country_codes",),
        expected_mock_model_names=(),
        expected_mock_source_names=(),
        expected_expected_model_names=("orders",),
        expected_mock_seed_names=("country_codes",),
    ),
    ExtractSqlTestCtesTestCase(
        description="extracts macro mocks from single string literal ctes",
        sql="""
        WITH
        __macro__country AS (SELECT '''US'''),
        __macro__empty AS (SELECT ''),
        __macro__literal_text AS (SELECT ''' + x + '''),
        __source__raw_orders AS (SELECT 1 AS order_id),
        __expected__orders AS (SELECT 1 AS order_id)
        SELECT 1
        """.strip(),
        expected_authored_cte_names=("__source__raw_orders",),
        expected_mock_model_names=(),
        expected_mock_source_names=("raw_orders",),
        expected_expected_model_names=("orders",),
        expected_macro_mocks={
            "country": "'US'",
            "empty": "",
            "literal_text": "' + x + '",
        },
    ),
    ExtractSqlTestCtesTestCase(
        description="extracts ctes from compact single line test sql",
        sql="""
        WITH
        helper AS (SELECT 1 AS order_id),
        __ref__orders AS (SELECT * FROM helper),
        __expected__order_items AS (SELECT order_id FROM __ref__orders)
        SELECT 1;
        """.strip(),
        expected_authored_cte_names=("helper", "__ref__orders"),
        expected_mock_model_names=("orders",),
        expected_mock_source_names=(),
        expected_expected_model_names=("order_items",),
    ),
    ExtractSqlTestCtesTestCase(
        description="extracts ctes with comments strings and nested parentheses",
        sql="""
        WITH /* leading */ helper_orders(order_id, note) AS (
          SELECT
            CAST('value ) inside string' AS VARCHAR) AS note,
            COALESCE(order_id, 0) AS order_id
          FROM raw_orders -- comment with ) and ,
        ) ,
        __source__raw_orders AS (SELECT * FROM helper_orders),
        __expected__orders AS (
          SELECT order_id, note FROM __source__raw_orders WHERE note != 'not ) done'
        )
        -- final comment before ceremonial select
        SELECT 1
        """.strip(),
        expected_authored_cte_names=("helper_orders", "__source__raw_orders"),
        expected_mock_model_names=(),
        expected_mock_source_names=("raw_orders",),
        expected_expected_model_names=("orders",),
    ),
    ExtractSqlTestCtesTestCase(
        description="extracts multiple expected targets with mixed whitespace",
        sql="""
        WITH
        __source__raw_orders AS(SELECT 1 AS order_id),__expected__orders AS(
          SELECT 1 AS order_id
        ),
        __expected__daily_revenue AS (SELECT SUM(1) AS revenue)
        SELECT 1;
        """.strip(),
        expected_authored_cte_names=("__source__raw_orders",),
        expected_mock_model_names=(),
        expected_mock_source_names=("raw_orders",),
        expected_expected_model_names=("orders", "daily_revenue"),
    ),
    ExtractSqlTestCtesTestCase(
        description="extracts ctes through nested helper chains and awkward comma placement",
        sql="""
        WITH source_seed(seed_id, payload) AS (
          SELECT * FROM (
            SELECT 1 AS seed_id, 'a,b,c' AS payload
            UNION ALL
            SELECT 2 AS seed_id, 'literal with ) and , chars' AS payload
          ) AS nested_seed
        )/* comma after block comment */,
        normalized_orders AS(
          SELECT seed_id AS order_id, CONCAT(payload, ')') AS note FROM source_seed
        )
        ,__source__raw_orders AS(
          SELECT * FROM normalized_orders WHERE note NOT IN ('x,y', 'z)')
        ), expected_rows AS (
          SELECT order_id, note FROM __source__raw_orders
          WHERE order_id IN (SELECT seed_id FROM source_seed WHERE seed_id > 0)
        ),
        __expected__orders AS (SELECT order_id, note FROM expected_rows)
        SELECT 1;
        """.strip(),
        expected_authored_cte_names=(
            "source_seed",
            "normalized_orders",
            "__source__raw_orders",
            "expected_rows",
        ),
        expected_mock_model_names=(),
        expected_mock_source_names=("raw_orders",),
        expected_expected_model_names=("orders",),
    ),
    ExtractSqlTestCtesTestCase(
        description="extracts ctes with inline comments around separators",
        sql="""
        WITH helper_a AS (SELECT 1 AS order_id) -- comment before comma
        , helper_b AS (SELECT order_id FROM helper_a /* ) , */)
        , __ref__orders AS (SELECT order_id FROM helper_b), -- trailing comma comment
        __expected__orders AS (
          SELECT order_id FROM __ref__orders WHERE order_id = (SELECT MAX(order_id) FROM helper_b)
        )
        SELECT 1
        """.strip(),
        expected_authored_cte_names=("helper_a", "helper_b", "__ref__orders"),
        expected_mock_model_names=("orders",),
        expected_mock_source_names=(),
        expected_expected_model_names=("orders",),
    ),
    ExtractSqlTestCtesTestCase(
        description="allows explicit union branches in expected ctes",
        sql="""
        WITH __source__raw_orders AS (
          SELECT 1 AS order_id, 'new' AS status
        ),
        __expected__orders AS (
          SELECT 1 AS order_id, 'new' AS status
          UNION ALL
          SELECT 2 AS order_id, 'paid' AS status
        )
        SELECT 1
        """.strip(),
        expected_authored_cte_names=("__source__raw_orders",),
        expected_mock_model_names=(),
        expected_mock_source_names=("raw_orders",),
        expected_expected_model_names=("orders",),
    ),
    ExtractSqlTestCtesTestCase(
        description="allows plain union with matching aliases in expected ctes",
        sql="""
        WITH __source__raw_orders AS (SELECT 1 AS order_id),
        __expected__orders AS (
          SELECT 1 AS order_id, 'created' AS status
          UNION
          SELECT 2 AS order_id, 'paid' AS status
        )
        SELECT 1
        """.strip(),
        expected_authored_cte_names=("__source__raw_orders",),
        expected_mock_model_names=(),
        expected_mock_source_names=("raw_orders",),
        expected_expected_model_names=("orders",),
    ),
    ExtractSqlTestCtesTestCase(
        description="allows cast expressions with explicit aliases in expected ctes",
        sql="""
        WITH __source__raw_orders AS (SELECT 1 AS order_id),
        __expected__orders AS (
          SELECT
            CAST(1 AS INTEGER) AS order_id,
            CAST('paid' AS VARCHAR) AS status
          UNION ALL
          SELECT
            CAST(2 AS INTEGER) AS order_id,
            CAST('created' AS VARCHAR) AS status
        )
        SELECT 1
        """.strip(),
        expected_authored_cte_names=("__source__raw_orders",),
        expected_mock_model_names=(),
        expected_mock_source_names=("raw_orders",),
        expected_expected_model_names=("orders",),
    ),
    ExtractSqlTestCtesTestCase(
        description="allows bare identifiers in expected cte projections",
        sql="""
        WITH expected_rows AS (SELECT 1 AS order_id, 'paid' AS status),
        __source__raw_orders AS (SELECT * FROM expected_rows),
        __expected__orders AS (
          SELECT order_id, status FROM expected_rows
        )
        SELECT 1
        """.strip(),
        expected_authored_cte_names=("expected_rows", "__source__raw_orders"),
        expected_mock_model_names=(),
        expected_mock_source_names=("raw_orders",),
        expected_expected_model_names=("orders",),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    TEST_CASES,
    ids=[case.description for case in TEST_CASES],
)
def test_given_sql_test_cte_variants_when_extracting_then_it_returns_expected_roles(
    test_case: ExtractSqlTestCtesTestCase,
) -> None:
    extracted_ctes: CompileSqlTestCtes = extract_sql_test_ctes(
        sql=test_case.sql,
        file_label="tests/unit/orders.sql",
    )

    assert (
        tuple(cte.name for cte in extracted_ctes.authored_ctes)
        == test_case.expected_authored_cte_names
    )
    assert extracted_ctes.mock_model_names == test_case.expected_mock_model_names
    assert extracted_ctes.mock_source_names == test_case.expected_mock_source_names
    assert extracted_ctes.mock_seed_names == test_case.expected_mock_seed_names
    assert extracted_ctes.expected_model_names == test_case.expected_expected_model_names
    assert extracted_ctes.macro_mocks == test_case.expected_macro_mocks


ERROR_TEST_CASES: list[ExtractSqlTestCtesErrorTestCase] = [
    ExtractSqlTestCtesErrorTestCase(
        description="raises when macro mock returns multiple columns",
        sql="""
        WITH __macro__country AS (SELECT 'US', 'CA'),
        __source__raw_orders AS (SELECT 1 AS order_id),
        __expected__orders AS (SELECT 1 AS order_id)
        SELECT 1
        """.strip(),
        expected_error_fragment=(
            "macro mock '__macro__country' must be a single SELECT string literal"
        ),
    ),
    ExtractSqlTestCtesErrorTestCase(
        description="raises when macro mock returns non string literal",
        sql="""
        WITH __macro__country AS (SELECT 123),
        __source__raw_orders AS (SELECT 1 AS order_id),
        __expected__orders AS (SELECT 1 AS order_id)
        SELECT 1
        """.strip(),
        expected_error_fragment=(
            "macro mock '__macro__country' must be a single SELECT string literal"
        ),
    ),
    ExtractSqlTestCtesErrorTestCase(
        description="raises when macro mock reads from a table",
        sql="""
        WITH __macro__country AS (SELECT 'US' FROM values_table),
        __source__raw_orders AS (SELECT 1 AS order_id),
        __expected__orders AS (SELECT 1 AS order_id)
        SELECT 1
        """.strip(),
        expected_error_fragment="with no FROM, UNION, or additional columns",
    ),
    ExtractSqlTestCtesErrorTestCase(
        description="raises when macro mock uses union",
        sql="""
        WITH __macro__country AS (SELECT 'US' UNION ALL SELECT 'CA'),
        __source__raw_orders AS (SELECT 1 AS order_id),
        __expected__orders AS (SELECT 1 AS order_id)
        SELECT 1
        """.strip(),
        expected_error_fragment="with no FROM, UNION, or additional columns",
    ),
    ExtractSqlTestCtesErrorTestCase(
        description="raises when test sql does not start with top level with",
        sql="SELECT 1",
        expected_error_fragment="must declare mock CTEs and one __expected__<model>",
    ),
    ExtractSqlTestCtesErrorTestCase(
        description="raises when cte body is unclosed",
        sql="""
        WITH __source__raw_orders AS (SELECT 1 AS order_id,
        __expected__orders AS (SELECT 1 AS order_id)
        SELECT 1
        """.strip(),
        expected_error_fragment="contains an unclosed parenthesis",
    ),
    ExtractSqlTestCtesErrorTestCase(
        description="raises when final select is not ceremonial select one",
        sql="""
        WITH __source__raw_orders AS (SELECT 1), __expected__orders AS (SELECT 1)
        SELECT 1 FROM __expected__orders
        """.strip(),
        expected_error_fragment="must end with a ceremonial top-level `SELECT 1`",
    ),
    ExtractSqlTestCtesErrorTestCase(
        description="raises when expected cte omits target name",
        sql="""
        WITH __source__raw_orders AS (SELECT 1), __expected__ AS (SELECT 1)
        SELECT 1
        """.strip(),
        expected_error_fragment="must use __expected__<model>",
    ),
    ExtractSqlTestCtesErrorTestCase(
        description="raises when expected cte uses select star",
        sql="""
        WITH __source__raw_orders AS (SELECT 1 AS order_id),
        __expected__orders AS (SELECT * FROM __source__raw_orders)
        SELECT 1
        """.strip(),
        expected_error_fragment=r"must not use SELECT \* in __expected__<model> CTEs",
    ),
    ExtractSqlTestCtesErrorTestCase(
        description="raises when union branch projection order differs",
        sql="""
        WITH __source__raw_orders AS (SELECT 1 AS order_id),
        __expected__orders AS (
          SELECT 1 AS order_id, 'paid' AS status
          UNION ALL
          SELECT 'created' AS status, 2 AS order_id
        )
        SELECT 1
        """.strip(),
        expected_error_fragment="projection names and order in every set-operation branch",
    ),
    ExtractSqlTestCtesErrorTestCase(
        description="raises when union branch projection alias is missing",
        sql="""
        WITH __source__raw_orders AS (SELECT 1 AS order_id),
        __expected__orders AS (
          SELECT CAST(1 AS INTEGER) AS order_id, CAST('paid' AS VARCHAR) AS status
          UNION ALL
          SELECT CAST(2 AS INTEGER), CAST('created' AS VARCHAR) AS status
        )
        SELECT 1
        """.strip(),
        expected_error_fragment="must alias every non-trivial __expected__<model> projection",
    ),
    ExtractSqlTestCtesErrorTestCase(
        description="raises when non union projection alias is missing",
        sql="""
        WITH __source__raw_orders AS (SELECT 1 AS order_id),
        __expected__orders AS (
          SELECT CAST(1 AS INTEGER), CAST('paid' AS VARCHAR) AS status
        )
        SELECT 1
        """.strip(),
        expected_error_fragment="must alias every non-trivial __expected__<model> projection",
    ),
    ExtractSqlTestCtesErrorTestCase(
        description="raises when expected branch is not a select query",
        sql="""
        WITH __source__raw_orders AS (SELECT 1 AS order_id),
        __expected__orders AS (
          SELECT 1 AS order_id
          UNION ALL
          VALUES (2)
        )
        SELECT 1
        """.strip(),
        expected_error_fragment="set-operation branch as a SELECT query",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    ERROR_TEST_CASES,
    ids=[case.description for case in ERROR_TEST_CASES],
)
def test_given_invalid_sql_test_cte_variants_when_extracting_then_it_raises_clear_errors(
    test_case: ExtractSqlTestCtesErrorTestCase,
) -> None:
    with pytest.raises(ValueError, match=test_case.expected_error_fragment):
        extract_sql_test_ctes(sql=test_case.sql, file_label="tests/unit/orders.sql")
