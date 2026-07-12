"""Logical SQL reference extraction helpers for compile semantics."""

from __future__ import annotations

from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models.core import CompileSqlReference
from sqlbuild.compiler.shared.helpers.sql_scanning import (
    find_matching_paren,
    skip_block_comment,
    skip_line_comment,
    skip_quoted_text,
)
from sqlbuild.shared.types import SqlReferenceKind

_CONTEXT: str = "SQL reference"
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
        if sql[index] in {"'", '"', "`"}:
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
    positions: list[int] = []
    token: str
    for token in ("__", "--", "/*", "'", '"', "`"):
        position: int = sql.find(token, start)
        if position >= 0:
            positions.append(position)
    return min(positions, default=len(sql))


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
    return (
        CompileSqlReference(
            ref_kind=ref_kind,
            ref_name=_parse_reference_name(raw_value=argument_values[0], ref_kind=ref_kind),
        ),
        closing_paren_index + 1,
    )


def ref_prefix(ref_kind: SqlReferenceKind | str) -> str:
    normalized_ref_kind: SqlReferenceKind = SqlReferenceKind(ref_kind)
    return _REFERENCE_PREFIX_BY_KIND[normalized_ref_kind]


def _split_top_level_arguments(raw_arguments: str) -> tuple[str, ...]:
    arguments: list[str] = []
    current: list[str] = []
    depth: int = 0
    index: int = 0
    while index < len(raw_arguments):
        character: str = raw_arguments[index]
        if character in {"'", '"', "`"}:
            quoted_end: int = skip_quoted_text(sql=raw_arguments, start=index, context=_CONTEXT)
            current.append(raw_arguments[index:quoted_end])
            index = quoted_end
            continue
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
        elif character == "," and depth == 0:
            argument_text: str = "".join(current).strip()
            if argument_text:
                arguments.append(argument_text)
            current = []
            index += 1
            continue
        current.append(character)
        index += 1

    final_argument: str = "".join(current).strip()
    if final_argument:
        arguments.append(final_argument)
    return tuple(arguments)


def _parse_reference_name(*, raw_value: str, ref_kind: SqlReferenceKind) -> str:
    stripped_value: str = raw_value.strip()
    paired_quote_character_count: int = 2
    if (
        len(stripped_value) >= paired_quote_character_count
        and stripped_value[0] == stripped_value[-1]
        and stripped_value[0]
        in {
            "'",
            '"',
        }
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
