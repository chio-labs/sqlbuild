from __future__ import annotations

import pytest

from sqlbuild.compiler.compile._helpers.scenarios.core import (
    extract_sql_scenario_expected_model_names,
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
            description="expected model scan without AS uses scenario wording",
            sql="WITH __source__raw_orders (SELECT 1 AS order_id) SELECT 1",
            expected_message="SQL scenario 'tests/scenarios/orders.sql' expected keyword AS",
        ),
        CteScannerMessageTestCase(
            description="expected model scan unclosed comment uses scenario wording",
            sql="WITH /* unfinished",
            expected_message="SQL scenario contains an unclosed block comment",
        ),
        CteScannerMessageTestCase(
            description="expected model scan leading unclosed comment uses scenario wording",
            sql="/* unfinished",
            expected_message="SQL scenario contains an unclosed block comment",
        ),
        CteScannerMessageTestCase(
            description="expected model scan without a target uses scenario wording",
            sql=(
                "WITH __source__raw_orders AS (SELECT 1 AS order_id), "
                "__expected__ AS (SELECT 1 AS order_id) SELECT 1"
            ),
            expected_message=(
                "SQL scenario 'tests/scenarios/orders.sql' must use __expected__<model> to "
                "identify a target"
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_malformed_scenario_ctes_when_scanning_expected_models_then_names_the_scenario(
    test_case: CteScannerMessageTestCase,
) -> None:
    with pytest.raises(CompileInputError) as error_info:
        _ = extract_sql_scenario_expected_model_names(
            sql=test_case.sql,
            file_label="tests/scenarios/orders.sql",
            syntax=_GENERIC_SQL_SYNTAX,
        )

    assert str(error_info.value) == test_case.expected_message


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
