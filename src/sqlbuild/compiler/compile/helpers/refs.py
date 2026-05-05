"""Logical SQL reference extraction helpers for compile semantics."""

from __future__ import annotations

from sqlbuild.compiler.compile.constants import (
    DBT_REF_CALL_NAME,
    REF_CALL_NAME,
    SOURCE_CALL_NAME,
    TABLE_FUNCTION_CALL_NAME,
    UDF_CALL_NAME,
)
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.helpers.sql_scanning import (
    find_matching_paren,
    skip_block_comment,
    skip_line_comment,
    skip_quoted_text,
)
from sqlbuild.compiler.compile.models import CompileSqlReference
from sqlbuild.compiler.compile.types import SqlReferenceKind

_CONTEXT: str = "SQL reference"


def extract_sql_references(sql: str) -> tuple[CompileSqlReference, ...]:
    """Return logical SQL refs found outside comments and quoted text."""

    references: list[CompileSqlReference] = []
    index: int = 0
    length: int = len(sql)
    while index < length:
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


def _parse_reference_at(*, sql: str, start: int) -> tuple[CompileSqlReference, int] | None:
    ref_kind: SqlReferenceKind | None = None
    if sql.startswith(f"{DBT_REF_CALL_NAME}(", start):
        ref_kind = SqlReferenceKind.DBT_REF
    elif sql.startswith(f"{SOURCE_CALL_NAME}(", start):
        ref_kind = SqlReferenceKind.SOURCE
    elif sql.startswith(f"{UDF_CALL_NAME}(", start):
        ref_kind = SqlReferenceKind.UDF
    elif sql.startswith(f"{TABLE_FUNCTION_CALL_NAME}(", start):
        ref_kind = SqlReferenceKind.TABLE_FUNCTION
    elif sql.startswith(f"{REF_CALL_NAME}(", start):
        ref_kind = SqlReferenceKind.REF
    if ref_kind is None:
        return None

    open_paren_index: int = start + len(ref_prefix(ref_kind))
    closing_paren_index: int = find_matching_paren(
        sql=sql, open_paren_index=open_paren_index, context=_CONTEXT
    )
    raw_arguments: str = sql[open_paren_index + 1 : closing_paren_index]
    argument_values: tuple[str, ...] = _split_top_level_arguments(raw_arguments)
    if len(argument_values) != 1:
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
    if normalized_ref_kind == SqlReferenceKind.DBT_REF:
        return DBT_REF_CALL_NAME
    if normalized_ref_kind == SqlReferenceKind.SOURCE:
        return SOURCE_CALL_NAME
    if normalized_ref_kind == SqlReferenceKind.UDF:
        return UDF_CALL_NAME
    if normalized_ref_kind == SqlReferenceKind.TABLE_FUNCTION:
        return TABLE_FUNCTION_CALL_NAME
    return REF_CALL_NAME


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
    if (
        len(stripped_value) >= 2
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
