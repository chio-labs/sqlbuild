"""SQL-native test compile-semantic extraction helpers."""

from __future__ import annotations

from functools import lru_cache

import sqlbuild._native as _native
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import (
    CompileSqlTestCte,
)
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
