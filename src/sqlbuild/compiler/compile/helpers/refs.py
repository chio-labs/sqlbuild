"""Logical SQL reference extraction helpers for compile semantics."""

from __future__ import annotations

from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import CompileSqlReference


def extract_sql_references(sql: str) -> tuple[CompileSqlReference, ...]:
    """Return logical SQL refs found outside comments and quoted text."""

    references: list[CompileSqlReference] = []
    index: int = 0
    length: int = len(sql)
    while index < length:
        if sql.startswith("--", index):
            newline_index: int = sql.find("\n", index)
            index = length if newline_index == -1 else newline_index + 1
            continue
        if sql.startswith("/*", index):
            closing_index: int = sql.find("*/", index + 2)
            if closing_index == -1:
                raise CompileInputError("SQL reference contains an unclosed block comment")
            index = closing_index + 2
            continue
        if sql[index] in {"'", '"', "`"}:
            index = _skip_quoted_text(sql=sql, start=index)
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
    ref_kind: str | None = None
    if sql.startswith("__dbt_ref(", start):
        ref_kind = "dbt_ref"
    elif sql.startswith("__source(", start):
        ref_kind = "source"
    elif sql.startswith("__ref(", start):
        ref_kind = "ref"
    if ref_kind is None:
        return None

    open_paren_index: int = start + len(ref_prefix(ref_kind))
    closing_paren_index: int = _find_matching_paren(sql=sql, open_paren_index=open_paren_index)
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


def ref_prefix(ref_kind: str) -> str:
    if ref_kind == "dbt_ref":
        return "__dbt_ref"
    if ref_kind == "source":
        return "__source"
    return "__ref"


def _find_matching_paren(*, sql: str, open_paren_index: int) -> int:
    depth: int = 1
    index: int = open_paren_index + 1
    length: int = len(sql)
    while index < length:
        if sql.startswith("--", index):
            newline_index: int = sql.find("\n", index)
            index = length if newline_index == -1 else newline_index + 1
            continue
        if sql.startswith("/*", index):
            closing_index: int = sql.find("*/", index + 2)
            if closing_index == -1:
                raise CompileInputError("SQL reference contains an unclosed block comment")
            index = closing_index + 2
            continue
        if sql[index] in {"'", '"', "`"}:
            index = _skip_quoted_text(sql=sql, start=index)
            continue
        if sql[index] == "(":
            depth += 1
        elif sql[index] == ")":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    raise CompileInputError("SQL reference contains an unclosed parenthesis")


def _split_top_level_arguments(raw_arguments: str) -> tuple[str, ...]:
    arguments: list[str] = []
    current: list[str] = []
    depth: int = 0
    index: int = 0
    while index < len(raw_arguments):
        character: str = raw_arguments[index]
        if character in {"'", '"', "`"}:
            quoted_end: int = _skip_quoted_text(sql=raw_arguments, start=index)
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


def _parse_reference_name(*, raw_value: str, ref_kind: str) -> str:
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


def _skip_quoted_text(*, sql: str, start: int) -> int:
    quote_character: str = sql[start]
    index: int = start + 1
    while index < len(sql):
        if sql[index] == quote_character:
            if (
                quote_character in {"'", '"'}
                and index + 1 < len(sql)
                and sql[index + 1] == quote_character
            ):
                index += 2
                continue
            return index + 1
        index += 1
    raise CompileInputError("SQL reference contains an unclosed quoted string")
