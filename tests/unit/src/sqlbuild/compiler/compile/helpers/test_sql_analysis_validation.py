from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.helpers.analysis.validation import validate_sql_syntax
from tests.unit.src.sqlbuild.compiler.compile.helpers._test_types import (
    ValidateSqlSyntaxTestCase,
)

_MODEL_NAME: str = "test_model"
_FILE_PATH: Path = Path("models/test_model.sql")


@pytest.mark.parametrize(
    "test_case",
    [
        ValidateSqlSyntaxTestCase(
            description="accepts simple select",
            query_sql='SELECT id, name FROM __ref("orders")',
            expected_valid=True,
        ),
        ValidateSqlSyntaxTestCase(
            description="accepts CTE chain",
            query_sql=(
                'WITH base AS (  SELECT id, name FROM __ref("orders")) SELECT id, name FROM base'
            ),
            expected_valid=True,
        ),
        ValidateSqlSyntaxTestCase(
            description="accepts source references",
            query_sql='SELECT id FROM __source("stripe__payments")',
            expected_valid=True,
        ),
        ValidateSqlSyntaxTestCase(
            description="accepts dbt ref references",
            query_sql='SELECT id FROM __dbt_ref("stg_orders")',
            expected_valid=True,
        ),
        ValidateSqlSyntaxTestCase(
            description="accepts udf references",
            query_sql='SELECT __udf("is_completed_order")(status) AS is_done FROM __ref("orders")',
            expected_valid=True,
        ),
        ValidateSqlSyntaxTestCase(
            description="accepts union queries",
            query_sql=('SELECT id FROM __ref("orders") UNION ALL SELECT id FROM __ref("returns")'),
            expected_valid=True,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_valid_sql_when_validating_syntax_then_does_not_raise(
    test_case: ValidateSqlSyntaxTestCase,
) -> None:
    validate_sql_syntax(
        query_sql=test_case.query_sql,
        model_name=_MODEL_NAME,
        file_path=_FILE_PATH,
    )

    assert test_case.expected_valid is True


@pytest.mark.parametrize(
    "test_case",
    [
        ValidateSqlSyntaxTestCase(
            description="rejects unclosed parenthesis",
            query_sql="SELECT id FROM (SELECT 1",
            expected_valid=False,
            expected_error_fragment="SQL syntax error in model 'test_model'",
        ),
        ValidateSqlSyntaxTestCase(
            description="rejects malformed select",
            query_sql="SELEC id FROM orders",
            expected_valid=False,
            expected_error_fragment="SQL syntax error in model 'test_model'",
        ),
        ValidateSqlSyntaxTestCase(
            description="rejects incomplete CTE",
            query_sql="WITH base AS ( SELECT id FROM orders",
            expected_valid=False,
            expected_error_fragment="SQL syntax error in model 'test_model'",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_sql_when_validating_syntax_then_raises_compile_error(
    test_case: ValidateSqlSyntaxTestCase,
) -> None:
    with pytest.raises(CompileInputError, match=test_case.expected_error_fragment):
        validate_sql_syntax(
            query_sql=test_case.query_sql,
            model_name=_MODEL_NAME,
            file_path=_FILE_PATH,
        )

    assert test_case.expected_valid is False
