"""Helpers for SQL analysis public-entry tests."""

from typing import cast

import sqlbuild._native as _native
from sqlbuild.compiler.sql_analysis.classes.binding_catalog import BindingCatalog
from sqlbuild.compiler.sql_analysis.models import SqlBindingDiagnostic, SqlBindingResult
from sqlbuild.compiler.sql_analysis.types import (
    NativeDiagnosticRow,
    NativePositionsModule,
    NativeProjectCatalog,
)


def nested_coalesce_sql(*, function_depth: int) -> str:
    expression: str = "value"
    for _ in range(function_depth):
        expression = f"COALESCE({expression}, 0)"
    return f"SELECT {expression} AS resolved_value FROM records"


def pool_catalog(dialect: str) -> NativeProjectCatalog:
    """Return a compile catalog, which normalizes batches on its analysis pool."""

    return BindingCatalog(
        dialect=dialect,
        quoted_ignore_case=False,
        known_functions=(),
        known_types=(),
        relations={},
    ).native


def without_catalog(dialect: str) -> None:
    """Return no catalog, which normalizes batches in turn."""

    _ = dialect


def mapped_binding_result(
    *, sql: str, dialect: str, rows: list[NativeDiagnosticRow]
) -> SqlBindingResult:
    """Native polyglot diagnostic rows mapped to SQLBuild binding diagnostics for `sql`."""

    mapped: list[NativeDiagnosticRow] = cast(NativePositionsModule, _native).binding_diagnostics(
        sql=sql, dialect=dialect, rows=rows
    )
    return SqlBindingResult(diagnostics=tuple(SqlBindingDiagnostic(*row) for row in mapped))
