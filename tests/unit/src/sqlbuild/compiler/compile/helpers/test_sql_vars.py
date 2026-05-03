"""Tests for SQL project variable substitution."""

from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.helpers.sql_vars import (
    substitute_sql_vars,
    validate_var_macro_collision,
)
from sqlbuild.compiler.compile.models import LoadedMacro
from tests.unit.src.sqlbuild.compiler.compile.helpers._test_types import (
    SubstituteSqlVarsErrorTestCase,
    SubstituteSqlVarsTestCase,
    VarMacroCollisionTestCase,
)

_FILE_PATH: Path = Path("models/test_model.sql")

SUBSTITUTION_TEST_CASES: list[SubstituteSqlVarsTestCase] = [
    SubstituteSqlVarsTestCase(
        description="replaces bare var in SQL expression",
        sql="SELECT * FROM orders WHERE region = @target_region",
        effective_vars={"target_region": "us-east-1"},
        expected_sql="SELECT * FROM orders WHERE region = us-east-1",
    ),
    SubstituteSqlVarsTestCase(
        description="replaces multiple vars",
        sql="SELECT * FROM @schema.@table",
        effective_vars={"schema": "staging", "table": "orders"},
        expected_sql="SELECT * FROM staging.orders",
    ),
    SubstituteSqlVarsTestCase(
        description="does not replace macro call with parens",
        sql="SELECT @my_macro('arg') FROM orders",
        effective_vars={"my_macro": "should_not_appear"},
        expected_sql="SELECT @my_macro('arg') FROM orders",
    ),
    SubstituteSqlVarsTestCase(
        description="returns sql unchanged when no vars defined",
        sql="SELECT @name FROM orders",
        effective_vars={},
        expected_sql="SELECT @name FROM orders",
    ),
    SubstituteSqlVarsTestCase(
        description="returns sql unchanged when no at signs present",
        sql="SELECT 1 FROM orders",
        effective_vars={"name": "value"},
        expected_sql="SELECT 1 FROM orders",
    ),
    SubstituteSqlVarsTestCase(
        description="skips var inside single-quoted string",
        sql="SELECT '@name' FROM orders",
        effective_vars={"name": "value"},
        expected_sql="SELECT '@name' FROM orders",
    ),
    SubstituteSqlVarsTestCase(
        description="skips var inside line comment",
        sql="-- @name\nSELECT 1",
        effective_vars={"name": "value"},
        expected_sql="-- @name\nSELECT 1",
    ),
    SubstituteSqlVarsTestCase(
        description="skips var inside block comment",
        sql="/* @name */ SELECT 1",
        effective_vars={"name": "value"},
        expected_sql="/* @name */ SELECT 1",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    SUBSTITUTION_TEST_CASES,
    ids=[case.description for case in SUBSTITUTION_TEST_CASES],
)
def test_given_sql_and_vars_when_substituting_then_returns_expected(
    test_case: SubstituteSqlVarsTestCase,
) -> None:
    result: str = substitute_sql_vars(
        sql=test_case.sql,
        file_path=_FILE_PATH,
        effective_vars=test_case.effective_vars,
    )

    assert result == test_case.expected_sql


@pytest.mark.parametrize(
    "test_case",
    [
        SubstituteSqlVarsErrorTestCase(
            description="raises on unknown var",
            sql="SELECT @unknown_var FROM orders",
            effective_vars={"other": "value"},
            expected_error_fragment="unknown project variable '@unknown_var'",
        ),
    ],
    ids=["raises on unknown var"],
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


@pytest.mark.parametrize(
    "test_case",
    [
        VarMacroCollisionTestCase(
            description="raises when var and macro names collide",
            var_names=("my_func",),
            macro_names=("my_func",),
            expected_valid=False,
            expected_error_fragment="collide with macro names",
        ),
    ],
    ids=["raises when var and macro names collide"],
)
def test_given_colliding_names_when_checking_collision_then_raises(
    test_case: VarMacroCollisionTestCase,
) -> None:
    effective_vars: dict[str, str] = {name: "value" for name in test_case.var_names}
    loaded_macros: dict[str, LoadedMacro] = {
        name: LoadedMacro(
            name=name,
            function=lambda: "",
            file_path=Path(f"macros/{name}.py"),
            relative_path=Path(f"macros/{name}.py"),
            raw_source="",
        )
        for name in test_case.macro_names
    }

    with pytest.raises(
        CompileInputError,
        match=test_case.expected_error_fragment or "",
    ):
        validate_var_macro_collision(
            effective_vars=effective_vars,
            loaded_macros=loaded_macros,
        )


@pytest.mark.parametrize(
    "test_case",
    [
        VarMacroCollisionTestCase(
            description="passes when no collision exists",
            var_names=("region",),
            macro_names=("my_func",),
            expected_valid=True,
        ),
    ],
    ids=["passes when no collision exists"],
)
def test_given_non_colliding_names_when_checking_collision_then_passes(
    test_case: VarMacroCollisionTestCase,
) -> None:
    effective_vars: dict[str, str] = {name: "value" for name in test_case.var_names}
    loaded_macros: dict[str, LoadedMacro] = {
        name: LoadedMacro(
            name=name,
            function=lambda: "",
            file_path=Path(f"macros/{name}.py"),
            relative_path=Path(f"macros/{name}.py"),
            raw_source="",
        )
        for name in test_case.macro_names
    }

    validate_var_macro_collision(
        effective_vars=effective_vars,
        loaded_macros=loaded_macros,
    )

    assert test_case.expected_valid
