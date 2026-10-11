from __future__ import annotations

import pytest

from sqlbuild.compiler.compile._helpers.sql_tests.core import (
    extract_sql_test_expected_model_names,
)
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax
from tests.unit.src.sqlbuild.compiler.compile._helpers._test_types import (
    CteScannerMessageTestCase,
)

_GENERIC_SQL_SYNTAX: SqlLexicalSyntax = SqlLexicalSyntax()


@pytest.mark.parametrize(
    "test_case",
    (
        CteScannerMessageTestCase(
            description="expected model scan without AS keeps sql test wording",
            sql="WITH __source__raw_orders (SELECT 1 AS order_id) SELECT 1",
            expected_message="SQL test 'tests/unit/orders.sql' expected keyword AS",
        ),
        CteScannerMessageTestCase(
            description="expected model scan without a target keeps sql test wording",
            sql=(
                "WITH __source__raw_orders AS (SELECT 1 AS order_id), "
                "__expected__ AS (SELECT 1 AS order_id) SELECT 1"
            ),
            expected_message=(
                "SQL test 'tests/unit/orders.sql' must use __expected__<model> to identify a target"
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_malformed_sql_test_ctes_when_scanning_expected_models_then_names_the_sql_test(
    test_case: CteScannerMessageTestCase,
) -> None:
    with pytest.raises(CompileInputError) as error_info:
        _ = extract_sql_test_expected_model_names(
            sql=test_case.sql, file_label="tests/unit/orders.sql", syntax=_GENERIC_SQL_SYNTAX
        )

    assert str(error_info.value) == test_case.expected_message
