"""Helpers for SQL analysis public-entry tests."""

from collections.abc import Callable, Mapping, Sequence
from typing import cast

import sqlbuild._native as _native
from sqlbuild._native import BindingCatalog
from sqlbuild.compiler.sql_analysis.models import SqlBindingDiagnostic, SqlBindingResult
from sqlbuild.compiler.sql_analysis.types import (
    NativeDiagnosticRow,
    NativeNormalizationRequest,
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


def normalize_analysis_sql_results(
    *,
    dialect: str | None,
    requests: Sequence[tuple[str, Mapping[str, str] | None, Mapping[str, str] | None]],
    catalog: NativeProjectCatalog | None,
) -> list[str | Exception]:
    """Normalize `(sql, stubs, placeholders)` natively in order, keeping failures in place."""

    normalize: Callable[..., list[str | Exception]] = getattr(
        catalog,
        "normalize_analysis_sqls",
        cast(NativePositionsModule, _native).normalize_analysis_sqls,
    )
    batch: list[NativeNormalizationRequest] = [
        (sql, dict(stubs or {}), dict(placeholders or {})) for sql, stubs, placeholders in requests
    ]
    return normalize(dialect=dialect or "generic", requests=batch)


def normalize_sql_for_polyglot(*, sql: str, dialect: str | None) -> str:
    """Return analysis-equivalent SQL for Polyglot's supported dialect surface."""

    return cast(NativePositionsModule, _native).normalize_dialect_sql(
        sql=sql, dialect=dialect or "generic"
    )


def normalize_analysis_sql(
    *,
    sql: str,
    dialect: str | None,
    stubs: Mapping[str, str] | None = None,
    placeholders: Mapping[str, str] | None = None,
) -> str:
    """Normalize one analysis SQL natively."""

    return cast(NativePositionsModule, _native).normalize_analysis_sql(
        {
            "sql": sql,
            "dialect": dialect or "generic",
            "stubs": dict(stubs or {}),
            "placeholders": dict(placeholders or {}),
        }
    )
