"""SQL project variable and environment interpolation helpers."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from sqlbuild.compiler.compile._helpers.render.declarations import (
    expand_declaration_references,
    expand_declaration_references_with_spans,
)
from sqlbuild.compiler.compile._helpers.render.macros import (
    expand_sql_macros,
    expand_sql_macros_with_spans,
)
from sqlbuild.compiler.compile.constants import (
    SQL_CONTEXT_NAME_EXTRA_TOKENS,
    SQL_IDENTIFIER_EXTRA_TOKEN,
    SQL_INTERPOLATION_TOKEN,
    SQL_QUOTE_TOKENS,
)
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.main._project_var_values import render_project_var_text
from sqlbuild.compiler.compile.models import (
    DeclarationResolutionContext,
    ExpansionSpan,
    LoadedMacro,
    MacroContext,
)
from sqlbuild.compiler.compile.types import TypedSqlValueRenderer
from sqlbuild.compiler.sql_analysis.main._is_identifier_character import (
    is_identifier_character as _is_identifier_continue,
)
from sqlbuild.compiler.sql_analysis.main._is_identifier_start import (
    is_identifier_start as _is_identifier_start,
)
from sqlbuild.compiler.sql_analysis.main._skip_block_comment import skip_block_comment
from sqlbuild.compiler.sql_analysis.main._skip_line_comment import skip_line_comment
from sqlbuild.compiler.sql_analysis.main._skip_quoted_text import skip_quoted_text
from sqlbuild.sql_values.types import CollectionRendering

_CONTEXT: str = "SQL interpolation"


def validate_var_macro_collision(
    *,
    effective_vars: dict[str, object],
    loaded_macros: dict[str, LoadedMacro],
) -> None:
    """Raise if any project var name collides with a macro name."""

    collisions: set[str] = set(effective_vars) & set(loaded_macros)
    if collisions:
        names: str = ", ".join(sorted(collisions))
        raise CompileInputError(
            f"project variable names collide with macro names: {names}. "
            f"Rename the variable or macro to avoid ambiguity."
        )


def expand_authored_sql(
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
) -> str:
    """Apply SQL interpolation and macro expansion to authored SQL text."""

    interpolated_sql: str = substitute_sql_vars(
        sql=sql,
        file_path=file_path,
        effective_vars=effective_vars,
        context_values=context_values,
    )
    declaration_expanded_sql: str = expand_declaration_references(
        sql=interpolated_sql,
        file_path=file_path,
        enums=declarations.enums if declarations is not None else {},
        constants=declarations.constants if declarations is not None else {},
        value_renderer=value_renderer,
        collection_rendering=collection_rendering,
        inaccessible_enums=(declarations.inaccessible_enums if declarations is not None else None),
        inaccessible_constants=(
            declarations.inaccessible_constants if declarations is not None else None
        ),
    )
    return expand_sql_macros(
        sql=declaration_expanded_sql,
        file_path=file_path,
        loaded_macros=loaded_macros,
        macro_context=macro_context,
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
    declaration_expanded_sql: str
    declaration_spans: tuple[ExpansionSpan, ...]
    declaration_expanded_sql, declaration_spans = expand_declaration_references_with_spans(
        sql=interpolated_sql,
        file_path=file_path,
        enums=declarations.enums if declarations is not None else {},
        constants=declarations.constants if declarations is not None else {},
        value_renderer=value_renderer,
        collection_rendering=collection_rendering,
        inaccessible_enums=(declarations.inaccessible_enums if declarations is not None else None),
        inaccessible_constants=(
            declarations.inaccessible_constants if declarations is not None else None
        ),
    )
    macro_expanded_sql: str
    macro_spans: tuple[ExpansionSpan, ...]
    macro_expanded_sql, macro_spans = expand_sql_macros_with_spans(
        sql=declaration_expanded_sql,
        file_path=file_path,
        loaded_macros=loaded_macros,
        macro_context=macro_context,
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

    rendered_sql: str
    rendered_sql, _spans = substitute_sql_vars_with_spans(
        sql=sql,
        file_path=file_path,
        effective_vars=effective_vars,
        context_values=context_values,
    )
    return rendered_sql


def substitute_sql_vars_with_spans(
    *,
    sql: str,
    file_path: Path,
    effective_vars: dict[str, object],
    context_values: Mapping[str, str | None] | None = None,
) -> tuple[str, tuple[ExpansionSpan, ...]]:
    """Replace SQL interpolation tokens, returning the span of every substitution."""

    if SQL_INTERPOLATION_TOKEN not in sql:
        return sql, ()

    parts: list[str] = []
    spans: list[ExpansionSpan] = []
    output_length: int = 0
    cursor: int = 0
    while cursor < len(sql):
        character: str = sql[cursor]
        if character in SQL_QUOTE_TOKENS:
            end: int = skip_quoted_text(sql=sql, start=cursor, context=_CONTEXT)
            segment_text: str
            segment_spans: tuple[ExpansionSpan, ...]
            segment_text, segment_spans = _interpolate_sql_segment(
                segment=sql[cursor:end],
                file_path=file_path,
                effective_vars=effective_vars,
                context_values=context_values,
            )
            parts.append(segment_text)
            segment_span: ExpansionSpan
            for segment_span in segment_spans:
                spans.append(
                    _rebased_span(span=segment_span, source_base=cursor, output_base=output_length)
                )
            output_length += len(segment_text)
            cursor = end
            continue
        if sql.startswith("--", cursor):
            end = skip_line_comment(sql=sql, start=cursor)
            parts.append(sql[cursor:end])
            output_length += end - cursor
            cursor = end
            continue
        if sql.startswith("/*", cursor):
            end = skip_block_comment(sql=sql, start=cursor, context=_CONTEXT)
            parts.append(sql[cursor:end])
            output_length += end - cursor
            cursor = end
            continue
        if sql.startswith("@@", cursor):
            rendered_token: str
            next_cursor: int
            rendered_token, next_cursor = _render_interpolation_token(
                sql=sql,
                start=cursor,
                file_path=file_path,
                effective_vars=effective_vars,
                context_values=context_values,
            )
            parts.append(rendered_token)
            spans.append(
                ExpansionSpan(
                    source_start=cursor,
                    source_end=next_cursor,
                    output_start=output_length,
                    output_end=output_length + len(rendered_token),
                )
            )
            output_length += len(rendered_token)
            cursor = next_cursor
            continue
        parts.append(character)
        output_length += 1
        cursor += 1
    return "".join(parts), tuple(spans)


def _rebased_span(*, span: ExpansionSpan, source_base: int, output_base: int) -> ExpansionSpan:
    return ExpansionSpan(
        source_start=span.source_start + source_base,
        source_end=span.source_end + source_base,
        output_start=span.output_start + output_base,
        output_end=span.output_end + output_base,
    )


def _interpolate_sql_segment(
    *,
    segment: str,
    file_path: Path,
    effective_vars: dict[str, object],
    context_values: Mapping[str, str | None] | None,
) -> tuple[str, tuple[ExpansionSpan, ...]]:
    if SQL_INTERPOLATION_TOKEN not in segment:
        return segment, ()
    parts: list[str] = []
    spans: list[ExpansionSpan] = []
    output_length: int = 0
    cursor: int = 0
    while cursor < len(segment):
        if segment.startswith("@@", cursor):
            rendered_token: str
            next_cursor: int
            rendered_token, next_cursor = _render_interpolation_token(
                sql=segment,
                start=cursor,
                file_path=file_path,
                effective_vars=effective_vars,
                context_values=context_values,
            )
            parts.append(rendered_token)
            spans.append(
                ExpansionSpan(
                    source_start=cursor,
                    source_end=next_cursor,
                    output_start=output_length,
                    output_end=output_length + len(rendered_token),
                )
            )
            output_length += len(rendered_token)
            cursor = next_cursor
            continue
        parts.append(segment[cursor])
        output_length += 1
        cursor += 1
    return "".join(parts), tuple(spans)


def _render_interpolation_token(
    *,
    sql: str,
    start: int,
    file_path: Path,
    effective_vars: dict[str, object],
    context_values: Mapping[str, str | None] | None,
) -> tuple[str, int]:
    if sql.startswith("@@@", start):
        name_start: int = start + 3
        if name_start < len(sql) and _is_identifier_start(sql[name_start]):
            name_end: int = _consume_identifier(sql=sql, start=name_start)
            return sql[start:name_end], name_end
        return "@@@", start + 3

    token_start: int = start + 2
    if sql.startswith("ENV:", token_start):
        env_name_start: int = token_start + len("ENV:")
        env_name_end: int = _consume_env_name(sql=sql, start=env_name_start)
        if env_name_end == env_name_start:
            raise CompileInputError(f"invalid environment interpolation token in '{file_path}'")
        env_name: str = sql[env_name_start:env_name_end]
        if env_name not in os.environ:
            raise CompileInputError(
                f"unknown environment variable '@@ENV:{env_name}' in '{file_path}'"
            )
        return os.environ[env_name], env_name_end

    if sql.startswith("CTX:", token_start):
        context_name_start: int = token_start + len("CTX:")
        context_name_end: int = _consume_context_name(sql=sql, start=context_name_start)
        if context_name_end == context_name_start:
            raise CompileInputError(f"invalid CTX interpolation token in '{file_path}'")
        context_name: str = sql[context_name_start:context_name_end]
        if context_values is None:
            raise CompileInputError(f"SQL text in '{file_path}' does not allow @@CTX templates")
        if context_name not in context_values:
            raise CompileInputError(
                f"SQL text in '{file_path}' references unknown CTX key '{context_name}'"
            )
        context_value: str | None = context_values[context_name]
        if context_value is None:
            raise CompileInputError(
                f"SQL text in '{file_path}' references CTX key '{context_name}' "
                "but no value is available"
            )
        return context_value, context_name_end

    if token_start < len(sql) and _is_identifier_start(sql[token_start]):
        name_end = _consume_identifier(sql=sql, start=token_start)
        var_name: str = sql[token_start:name_end]
        if var_name not in effective_vars:
            raise CompileInputError(
                f"unknown project variable '@@{var_name}' in '{file_path}'. "
                f"Available vars: {', '.join(sorted(effective_vars)) or 'none'}"
            )
        try:
            return render_project_var_text(
                value=effective_vars[var_name],
                label=f"SQL variable '@@{var_name}'",
            ), name_end
        except ValueError as error:
            raise CompileInputError(str(error)) from error

    return "@@", start + 2


def _consume_identifier(*, sql: str, start: int) -> int:
    cursor: int = start + 1
    while cursor < len(sql) and _is_identifier_continue(sql[cursor]):
        cursor += 1
    return cursor


def _consume_env_name(*, sql: str, start: int) -> int:
    cursor: int = start
    while cursor < len(sql) and (
        sql[cursor].isalnum() or sql[cursor] == SQL_IDENTIFIER_EXTRA_TOKEN
    ):
        cursor += 1
    return cursor


def _consume_context_name(*, sql: str, start: int) -> int:
    cursor: int = start
    while cursor < len(sql) and (
        sql[cursor].isalnum() or sql[cursor] in SQL_CONTEXT_NAME_EXTRA_TOKENS
    ):
        cursor += 1
    return cursor
