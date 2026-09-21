from __future__ import annotations

import pytest

from sqlbuild.compiler.compile._helpers.sql_tests.core import extract_sql_test_ctes
from sqlbuild.compiler.compile._helpers.sql_tests.native import extract_expanded_sql_tests
from sqlbuild.compiler.compile.models import CompileSqlTestCtes
from sqlbuild.compiler.compile.types import SqlTestMode
from tests.unit.src.sqlbuild.compiler.compile._helpers._test_types import (
    ExpectedBooleanTestCase,
    NativeSqlTestExtractionParityTestCase,
)


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
def test_given_expanded_sql_tests_when_native_batch_extracting_then_matches_reference_semantics(
    test_case: NativeSqlTestExtractionParityTestCase,
) -> None:
    expected: CompileSqlTestCtes = extract_sql_test_ctes(
        sql=test_case.sql,
        file_label="tests/unit/example.sql",
        mode=test_case.mode,
    )

    actual: tuple[CompileSqlTestCtes, ...] = extract_expanded_sql_tests(
        ((test_case.sql, "tests/unit/example.sql", test_case.mode),)
    )

    assert (actual == (expected,)) is test_case.expected_matches


@pytest.mark.parametrize(
    "test_case",
    [ExpectedBooleanTestCase(description="cross-check diagnostic matches", expected_result=True)],
    ids=lambda case: case.description,
)
def test_given_cross_check_dependency_when_native_batch_extracting_then_matches_reference_diagnostic(
    test_case: ExpectedBooleanTestCase,
) -> None:
    sql: str = (
        "WITH __source__raw_orders AS (SELECT 1 AS order_id), "
        "__expected__orders AS (SELECT 1 AS order_id), "
        "helper AS (SELECT order_id FROM __expected__orders), "
        "__assert__same AS (SELECT order_id FROM helper) SELECT 1"
    )
    with pytest.raises(ValueError) as reference_error:
        extract_sql_test_ctes(
            sql=sql,
            file_label="tests/unit/example.sql",
            mode=SqlTestMode.MODEL,
        )

    with pytest.raises(ValueError) as native_error:
        extract_expanded_sql_tests(((sql, "tests/unit/example.sql", SqlTestMode.MODEL),))

    assert (str(native_error.value) == str(reference_error.value)) is test_case.expected_result


@pytest.mark.parametrize(
    "test_case",
    [
        ExpectedBooleanTestCase(
            description="comma-separated cross-check diagnostic matches",
            expected_result=True,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_comma_separated_cross_check_dependency_when_extracting_then_native_matches_reference_diagnostic(
    test_case: ExpectedBooleanTestCase,
) -> None:
    sql: str = (
        "WITH __source__orders AS (SELECT 1 AS id), "
        "__expected__orders AS (SELECT 1 AS id), "
        "__assert__valid AS ("
        "SELECT expected.id FROM __source__orders source, __expected__orders expected"
        ") SELECT 1"
    )
    with pytest.raises(ValueError) as reference_error:
        extract_sql_test_ctes(
            sql=sql,
            file_label="tests/unit/example.sql",
            mode=SqlTestMode.MODEL,
        )

    with pytest.raises(ValueError) as native_error:
        extract_expanded_sql_tests(((sql, "tests/unit/example.sql", SqlTestMode.MODEL),))

    assert (str(native_error.value) == str(reference_error.value)) is test_case.expected_result
