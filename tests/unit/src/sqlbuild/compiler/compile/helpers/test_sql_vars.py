"""Tests for SQL project variable interpolation."""

from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.helpers.sql_vars import (
    substitute_sql_vars,
)
from tests.unit.src.sqlbuild.compiler.compile.helpers._test_types import (
    SubstituteSqlVarsErrorTestCase,
    SubstituteSqlVarsTestCase,
)

_FILE_PATH: Path = Path("models/test_model.sql")

SUBSTITUTION_TEST_CASES: list[SubstituteSqlVarsTestCase] = [
    SubstituteSqlVarsTestCase(
        description="replaces project var in SQL expression",
        sql="SELECT * FROM orders WHERE region = @@target_region",
        effective_vars={"target_region": "us-east-1"},
        expected_sql="SELECT * FROM orders WHERE region = us-east-1",
    ),
    SubstituteSqlVarsTestCase(
        description="replaces multiple vars",
        sql="SELECT * FROM @@schema.@@table",
        effective_vars={"schema": "staging", "table": "orders"},
        expected_sql="SELECT * FROM staging.orders",
    ),
    SubstituteSqlVarsTestCase(
        description="replaces env var in quoted SQL string",
        sql="SELECT '@@ENV:USER_NAME' AS loaded_by",
        effective_vars={},
        environment_variables={"USER_NAME": "runner"},
        expected_sql="SELECT 'runner' AS loaded_by",
    ),
    SubstituteSqlVarsTestCase(
        description="does not replace macro call with parens",
        sql="SELECT @my_macro('arg') FROM orders",
        effective_vars={"my_macro": "should_not_appear"},
        expected_sql="SELECT @my_macro('arg') FROM orders",
    ),
    SubstituteSqlVarsTestCase(
        description="does not replace single at placeholder syntax",
        sql="SELECT @name FROM orders",
        effective_vars={"name": "value"},
        expected_sql="SELECT @name FROM orders",
    ),
    SubstituteSqlVarsTestCase(
        description="returns sql unchanged when no interpolation tokens present",
        sql="SELECT 1 FROM orders",
        effective_vars={"name": "value"},
        expected_sql="SELECT 1 FROM orders",
    ),
    SubstituteSqlVarsTestCase(
        description="replaces var inside single-quoted string",
        sql="SELECT '@@name' FROM orders",
        effective_vars={"name": "value"},
        expected_sql="SELECT 'value' FROM orders",
    ),
    SubstituteSqlVarsTestCase(
        description="skips interpolation inside line comment",
        sql="-- @@name\nSELECT 1",
        effective_vars={"name": "value"},
        expected_sql="-- @@name\nSELECT 1",
    ),
    SubstituteSqlVarsTestCase(
        description="skips interpolation inside block comment",
        sql="/* @@name */ SELECT 1",
        effective_vars={"name": "value"},
        expected_sql="/* @@name */ SELECT 1",
    ),
    SubstituteSqlVarsTestCase(
        description="preserves deferred engine placeholder",
        sql="SELECT * FROM orders WHERE ds >= @@@partition_start",
        effective_vars={"partition_start": "should_not_appear"},
        expected_sql="SELECT * FROM orders WHERE ds >= @@@partition_start",
    ),
]

SUBSTITUTE_SQL_VARS_ERROR_TEST_CASES: list[SubstituteSqlVarsErrorTestCase] = [
    SubstituteSqlVarsErrorTestCase(
        description="raises on unknown var",
        sql="SELECT @@unknown_var FROM orders",
        effective_vars={"other": "value"},
        expected_error_fragment="unknown project variable '@@unknown_var'",
    ),
    SubstituteSqlVarsErrorTestCase(
        description="raises on CTX token",
        sql="SELECT @@CTX:model.name FROM orders",
        effective_vars={},
        expected_error_fragment="does not allow @@CTX templates",
    ),
    SubstituteSqlVarsErrorTestCase(
        description="raises on unknown env var",
        sql="SELECT '@@ENV:SQLBUILD_MISSING_ENV'",
        effective_vars={},
        expected_error_fragment="unknown environment variable '@@ENV:SQLBUILD_MISSING_ENV'",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    SUBSTITUTION_TEST_CASES,
    ids=[case.description for case in SUBSTITUTION_TEST_CASES],
)
def test_given_sql_and_vars_when_substituting_then_returns_expected(
    test_case: SubstituteSqlVarsTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment_name: str
    environment_value: str
    for environment_name, environment_value in test_case.environment_variables.items():
        monkeypatch.setenv(environment_name, environment_value)

    result: str = substitute_sql_vars(
        sql=test_case.sql,
        file_path=_FILE_PATH,
        effective_vars=test_case.effective_vars,
    )

    assert result == test_case.expected_sql


@pytest.mark.parametrize(
    "test_case",
    SUBSTITUTE_SQL_VARS_ERROR_TEST_CASES,
    ids=[case.description for case in SUBSTITUTE_SQL_VARS_ERROR_TEST_CASES],
)
def test_given_missing_var_when_substituting_then_raises(
    test_case: SubstituteSqlVarsErrorTestCase,
) -> None:
    with pytest.raises(CompileInputError, match=test_case.expected_error_fragment):
        substitute_sql_vars(
            sql=test_case.sql,
            file_path=_FILE_PATH,
            effective_vars=test_case.effective_vars,
        )
