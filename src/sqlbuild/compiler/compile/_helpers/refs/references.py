"""Logical SQL reference extraction helpers for compile semantics."""

from __future__ import annotations

import re

from sqlbuild.compiler.compile.constants import (
    SQL_ARGUMENT_SEPARATOR_TOKEN,
    SQL_CLOSE_PAREN_TOKEN,
    SQL_OPEN_PAREN_TOKEN,
    SQL_QUOTE_TOKENS,
    SQL_REFERENCE_NAME_QUOTE_TOKENS,
)
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import CompileSqlReference
from sqlbuild.compiler.references.types import SqlReferenceKind
from sqlbuild.compiler.sql_analysis.main._find_matching_paren import find_matching_paren
from sqlbuild.compiler.sql_analysis.main._skip_block_comment import skip_block_comment
from sqlbuild.compiler.sql_analysis.main._skip_line_comment import skip_line_comment
from sqlbuild.compiler.sql_analysis.main._skip_quoted_text import skip_quoted_text

_CONTEXT: str = "SQL reference"
_DOUBLE_QUOTE_TOKEN: str = '"'
_PAIRED_QUOTE_CHARACTER_COUNT: int = 2
_REFERENCE_PREFIXES: tuple[tuple[str, SqlReferenceKind], ...] = (
    ("__dbt_ref(", SqlReferenceKind.DBT_REF),
    ("__table_fn(", SqlReferenceKind.TABLE_FUNCTION),
    ("__source(", SqlReferenceKind.SOURCE),
    ("__seed(", SqlReferenceKind.SEED),
    ("__udf(", SqlReferenceKind.UDF),
    ("__ref(", SqlReferenceKind.REF),
)
_REFERENCE_PREFIX_BY_KIND: dict[SqlReferenceKind, str] = {
    ref_kind: prefix[:-1] for prefix, ref_kind in _REFERENCE_PREFIXES
}
_REFERENCE_SCAN_PATTERN: re.Pattern[str] = re.compile(r"__|--|/\*|'|\"|`")


def extract_sql_references(sql: str) -> tuple[CompileSqlReference, ...]:
    """Return logical SQL refs found outside comments and quoted text."""

    references: list[CompileSqlReference] = []
    index: int = 0
    length: int = len(sql)
    while index < length:
        index = _next_reference_scan_position(sql=sql, start=index)
        if index >= length:
            break
        if sql.startswith("--", index):
            index = skip_line_comment(sql=sql, start=index)
            continue
        if sql.startswith("/*", index):
            index = skip_block_comment(sql=sql, start=index, context=_CONTEXT)
            continue
        if sql[index] in SQL_QUOTE_TOKENS:
            index = skip_quoted_text(sql=sql, start=index, context=_CONTEXT)
            continue

        parsed_reference: tuple[CompileSqlReference, int] | None = _parse_reference_at(
            sql=sql,
            start=index,
        )
        if parsed_reference is None:
            index += 1
            continue
        references.append(parsed_reference[0])
        index = parsed_reference[1]
    return tuple(references)


def _next_reference_scan_position(*, sql: str, start: int) -> int:
    match: re.Match[str] | None = _REFERENCE_SCAN_PATTERN.search(sql, start)
    return match.start() if match is not None else len(sql)


def _parse_reference_at(*, sql: str, start: int) -> tuple[CompileSqlReference, int] | None:
    ref_kind: SqlReferenceKind | None = None
    prefix: str
    for prefix, candidate_kind in _REFERENCE_PREFIXES:
        if sql.startswith(prefix, start):
            ref_kind = candidate_kind
            break
    if ref_kind is None:
        return None

    open_paren_index: int = start + len(_REFERENCE_PREFIX_BY_KIND[ref_kind])
    closing_paren_index: int = find_matching_paren(
        sql=sql, open_paren_index=open_paren_index, context=_CONTEXT
    )
    raw_arguments: str = sql[open_paren_index + 1 : closing_paren_index]
    argument_values: tuple[str, ...] = _split_top_level_arguments(raw_arguments)
    two_argument_count: int = 2
    if ref_kind == SqlReferenceKind.DBT_REF:
        if len(argument_values) not in {1, two_argument_count}:
            raise CompileInputError(
                f"{ref_prefix(ref_kind)} must contain one name argument or package/name arguments"
            )
        if len(argument_values) == two_argument_count:
            return (
                CompileSqlReference(
                    ref_kind=ref_kind,
                    ref_package=_parse_reference_name(
                        raw_value=argument_values[0], ref_kind=ref_kind
                    ),
                    ref_name=_parse_reference_name(raw_value=argument_values[1], ref_kind=ref_kind),
                ),
                closing_paren_index + 1,
            )
    elif len(argument_values) != 1:
        raise CompileInputError(f"{ref_prefix(ref_kind)} must contain exactly one name argument")
    call_argument_count: int | None = None
    if ref_kind == SqlReferenceKind.TABLE_FUNCTION:
        call_suffix_start: int = _skip_whitespace(sql=sql, start=closing_paren_index + 1)
        if call_suffix_start >= len(sql) or sql[call_suffix_start] != SQL_OPEN_PAREN_TOKEN:
            raise CompileInputError(f"{ref_prefix(ref_kind)} must be followed by an argument list")
        call_suffix_end: int = find_matching_paren(
            sql=sql,
            open_paren_index=call_suffix_start,
            context="SQL table function call",
        )
        call_argument_count = len(
            _split_top_level_arguments(sql[call_suffix_start + 1 : call_suffix_end])
        )
    return (
        CompileSqlReference(
            ref_kind=ref_kind,
            ref_name=_parse_reference_name(raw_value=argument_values[0], ref_kind=ref_kind),
            call_argument_count=call_argument_count,
        ),
        closing_paren_index + 1,
    )


def ref_prefix(ref_kind: SqlReferenceKind | str) -> str:
    normalized_ref_kind: SqlReferenceKind = SqlReferenceKind(ref_kind)
    return _REFERENCE_PREFIX_BY_KIND[normalized_ref_kind]


def _skip_whitespace(*, sql: str, start: int) -> int:
    index: int = start
    while index < len(sql) and sql[index].isspace():
        index += 1
    return index


def _split_top_level_arguments(raw_arguments: str) -> tuple[str, ...]:
    arguments: list[str] = []
    current: list[str] = []
    depth: int = 0
    index: int = 0
    saw_separator: bool = False
    while index < len(raw_arguments):
        if raw_arguments.startswith("--", index):
            index = skip_line_comment(sql=raw_arguments, start=index)
            current.append(" ")
            continue
        if raw_arguments.startswith("/*", index):
            index = skip_block_comment(sql=raw_arguments, start=index, context=_CONTEXT)
            current.append(" ")
            continue
        character: str = raw_arguments[index]
        if character in SQL_QUOTE_TOKENS:
            quoted_end: int = skip_quoted_text(sql=raw_arguments, start=index, context=_CONTEXT)
            current.append(raw_arguments[index:quoted_end])
            index = quoted_end
            continue
        if character == SQL_OPEN_PAREN_TOKEN:
            depth += 1
        elif character == SQL_CLOSE_PAREN_TOKEN:
            depth -= 1
        elif character == SQL_ARGUMENT_SEPARATOR_TOKEN and depth == 0:
            argument_text: str = "".join(current).strip()
            if not argument_text:
                raise CompileInputError(f"{_CONTEXT} contains an empty argument")
            arguments.append(argument_text)
            current = []
            saw_separator = True
            index += 1
            continue
        current.append(character)
        index += 1

    final_argument: str = "".join(current).strip()
    if final_argument:
        arguments.append(final_argument)
    elif saw_separator:
        raise CompileInputError(f"{_CONTEXT} contains an empty argument")
    return tuple(arguments)


def _parse_reference_name(*, raw_value: str, ref_kind: SqlReferenceKind) -> str:
    stripped_value: str = raw_value.strip()
    if ref_kind == SqlReferenceKind.TABLE_FUNCTION and not (
        len(stripped_value) >= _PAIRED_QUOTE_CHARACTER_COUNT
        and stripped_value[0] == stripped_value[-1] == _DOUBLE_QUOTE_TOKEN
    ):
        raise CompileInputError(f"{ref_prefix(ref_kind)} name argument must be double quoted")
    if (
        len(stripped_value) >= _PAIRED_QUOTE_CHARACTER_COUNT
        and stripped_value[0] == stripped_value[-1]
        and stripped_value[0] in SQL_REFERENCE_NAME_QUOTE_TOKENS
    ):
        return stripped_value[1:-1]
    if (
        stripped_value
        and stripped_value.replace("_", "a").isalnum()
        and stripped_value[0].isalpha()
    ):
        return stripped_value
    raise CompileInputError(
        f"{ref_prefix(ref_kind)} name argument must be a quoted string or identifier"
    )
