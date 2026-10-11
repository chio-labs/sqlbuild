"""SQL-native test compile-semantic extraction helpers."""

from __future__ import annotations

from functools import lru_cache

import sqlbuild._native as _native
from sqlbuild.compiler.compile.constants import (
    DEFAULT_SQL_TEST_MODE,
)
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import (
    CompileSqlTestCte,
)
from sqlbuild.compiler.compile.types import SqlTestMode
from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax


@lru_cache(maxsize=4096)
def extract_unclassified_sql_test_ctes(
    *, sql: str, file_label: str, syntax: SqlLexicalSyntax
) -> tuple[CompileSqlTestCte, ...]:
    """Extract raw top-level CTEs before mode-specific classification."""

    error: str | None
    ctes: list[tuple[str, str]]
    error, ctes = _native.scope_test_ctes([(sql, file_label)], syntax.native_mapping)[0]
    if error is not None:
        raise CompileInputError(error)
    return tuple(CompileSqlTestCte(name=name, sql_body=body) for name, body in ctes)


def extract_sql_test_expected_model_names(
    *,
    sql: str,
    file_label: str,
    syntax: SqlLexicalSyntax,
    mode: SqlTestMode = DEFAULT_SQL_TEST_MODE,
) -> tuple[str, ...]:
    """Extract explicit expected-model relationships without inspecting CTE bodies."""

    if mode is not SqlTestMode.MODEL:
        return ()
    return scanned_expected_model_names(
        sql=sql, file_label=file_label, scenario=False, syntax=syntax
    )


def scanned_expected_model_names(
    *, sql: str, file_label: str, scenario: bool, syntax: SqlLexicalSyntax
) -> tuple[str, ...]:
    """A SQL test's or scenario's `__expected__<model>` names, raising the scan's error."""

    error: str | None
    names: list[str]
    error, names = _native.scope_expected_model_names(
        [(sql, file_label)], scenario, syntax.native_mapping
    )[0]
    if error is not None:
        raise CompileInputError(error)
    return tuple(names)
