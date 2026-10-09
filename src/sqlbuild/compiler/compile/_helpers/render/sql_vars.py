"""SQL project variable and environment interpolation helpers."""

from __future__ import annotations

import sys
import unicodedata
from collections.abc import Mapping
from pathlib import Path

import sqlbuild._native as _native
from sqlbuild.compiler.authored_values.main._project_var_values import render_project_var_text
from sqlbuild.compiler.compile._helpers.render.declarations import (
    expand_scanned_declaration_references,
)
from sqlbuild.compiler.compile._helpers.render.macros import (
    expand_sql_macros_result,
    expand_sql_macros_with_spans,
)
from sqlbuild.compiler.compile._helpers.render.templating import record_template_reads
from sqlbuild.compiler.compile.classes.unicode_environment import UnicodeEnvironment
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import (
    AuthoredSqlExpansionResult,
    DeclarationExpansionResult,
    DeclarationResolutionContext,
    DeclarationScopeResolver,
    ExpansionSpan,
    LoadedMacro,
    MacroContext,
    MacroExpansionResult,
    SqlInterpolation,
)
from sqlbuild.compiler.compile.types import TypedSqlValueRenderer
from sqlbuild.compiler.model_loop.main._scan_native_declaration_references import (
    scan_native_declaration_references,
)
from sqlbuild.sql_values.types import CollectionRendering


def expand_authored_sql_result(  # noqa: PLR0913
    *,
    sql: str,
    file_path: Path,
    effective_vars: dict[str, object],
    loaded_macros: dict[str, LoadedMacro],
    macro_context: MacroContext,
    value_renderer: TypedSqlValueRenderer,
    collection_rendering: CollectionRendering,
    context_values: Mapping[str, str | None] | None = None,
    declarations: DeclarationResolutionContext | None = None,
    declaration_resolver: DeclarationScopeResolver | None = None,
) -> AuthoredSqlExpansionResult:
    """Apply all expansion passes and retain facts emitted by those passes."""

    interpolated_sql: str = substitute_sql_vars(
        sql=sql,
        file_path=file_path,
        effective_vars=effective_vars,
        context_values=context_values,
    )
    declaration_context: DeclarationResolutionContext = (
        declarations or DeclarationResolutionContext()
    )
    declaration_result: DeclarationExpansionResult = expand_scanned_declaration_references(
        sql=interpolated_sql,
        references=scan_native_declaration_references(sqls=(interpolated_sql,))[0],
        file_path=file_path,
        declarations=declaration_context,
        value_renderer=value_renderer,
        collection_rendering=collection_rendering,
    )
    macro_result: MacroExpansionResult = expand_sql_macros_result(
        sql=declaration_result.sql,
        file_path=file_path,
        loaded_macros=loaded_macros,
        macro_context=macro_context,
        declaration_resolver=declaration_resolver,
        consumer=declaration_context.consumer,
    )
    return AuthoredSqlExpansionResult(
        sql=macro_result.sql,
        usages=tuple(dict.fromkeys((*declaration_result.usages, *macro_result.usages))),
        argument_references=macro_result.argument_references,
    )


def expand_authored_sql_with_spans(
    *,
    sql: str,
    file_path: Path,
    effective_vars: dict[str, object],
    loaded_macros: dict[str, LoadedMacro],
    macro_context: MacroContext,
    value_renderer: TypedSqlValueRenderer,
    collection_rendering: CollectionRendering,
    context_values: Mapping[str, str | None] | None = None,
    declarations: DeclarationResolutionContext | None = None,
    declaration_resolver: DeclarationScopeResolver | None = None,
) -> tuple[str, tuple[tuple[ExpansionSpan, ...], ...]]:
    """Expand authored SQL, returning each pass's substitution spans in order."""

    interpolated_sql: str
    interpolation_spans: tuple[ExpansionSpan, ...]
    interpolated_sql, interpolation_spans = substitute_sql_vars_with_spans(
        sql=sql,
        file_path=file_path,
        effective_vars=effective_vars,
        context_values=context_values,
    )
    declaration_result: DeclarationExpansionResult = expand_scanned_declaration_references(
        sql=interpolated_sql,
        references=scan_native_declaration_references(sqls=(interpolated_sql,))[0],
        file_path=file_path,
        declarations=DeclarationResolutionContext(
            enums=declarations.enums if declarations is not None else {},
            constants=declarations.constants if declarations is not None else {},
            inaccessible_enums=declarations.inaccessible_enums if declarations is not None else {},
            inaccessible_constants=(
                declarations.inaccessible_constants if declarations is not None else {}
            ),
        ),
        value_renderer=value_renderer,
        collection_rendering=collection_rendering,
    )
    declaration_expanded_sql: str = declaration_result.sql
    declaration_spans: tuple[ExpansionSpan, ...] = declaration_result.spans
    macro_expanded_sql: str
    macro_spans: tuple[ExpansionSpan, ...]
    macro_expanded_sql, macro_spans = expand_sql_macros_with_spans(
        sql=declaration_expanded_sql,
        file_path=file_path,
        loaded_macros=loaded_macros,
        macro_context=macro_context,
        declaration_resolver=declaration_resolver,
    )
    return macro_expanded_sql, (interpolation_spans, declaration_spans, macro_spans)


def substitute_sql_vars(
    *,
    sql: str,
    file_path: Path,
    effective_vars: dict[str, object],
    context_values: Mapping[str, str | None] | None = None,
) -> str:
    """Replace @@name, @@ENV:NAME, and allowed @@CTX:name references in SQL text."""

    return applied_interpolation(
        interpolate_sql_batch(
            sqls=((sql, file_path),),
            effective_vars=effective_vars,
            context_values=context_values,
        )[0]
    )


def substitute_sql_vars_with_spans(
    *,
    sql: str,
    file_path: Path,
    effective_vars: dict[str, object],
    context_values: Mapping[str, str | None] | None = None,
) -> tuple[str, tuple[ExpansionSpan, ...]]:
    """Replace SQL interpolation tokens, returning the span of every substitution."""

    interpolation: SqlInterpolation = interpolate_sql_batch(
        sqls=((sql, file_path),), effective_vars=effective_vars, context_values=context_values
    )[0]
    return applied_interpolation(interpolation), interpolation.spans


def interpolate_sql_batch(
    *,
    sqls: tuple[tuple[str, Path], ...],
    effective_vars: dict[str, object],
    context_values: Mapping[str, str | None] | None = None,
) -> tuple[SqlInterpolation, ...]:
    """Interpolate every `(sql, file path)` natively; errors wait in their result."""

    rows = _native.interpolate_sql_batch(
        [(sql, str(file_path)) for sql, file_path in sqls],
        (effective_vars, UnicodeEnvironment(), context_values, _render_variable),
        (sys.version_info[0], sys.version_info[1]),
        unicodedata.unidata_version,
    )
    return tuple(
        SqlInterpolation(
            sql=rendered if rendered is not None else sql,
            spans=tuple(ExpansionSpan(*span) for span in spans),
            reads=tuple(reads),
            error=error,
        )
        for (sql, _file_path), (rendered, spans, reads, error) in zip(sqls, rows, strict=True)
    )


def applied_interpolation(interpolation: SqlInterpolation) -> str:
    """Record the interpolation's environment and context reads, then return or raise it."""

    record_template_reads(interpolation.reads)
    if interpolation.error is not None:
        raise CompileInputError(interpolation.error, bridge_independent=True)
    return interpolation.sql


def _render_variable(value: object, label: str) -> str:
    return render_project_var_text(value=value, label=label)
