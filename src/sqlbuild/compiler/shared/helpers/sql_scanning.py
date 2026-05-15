"""Shared SQL character-level scanning primitives for compiler helpers."""

from __future__ import annotations

from sqlbuild.compiler.compile.exceptions import CompileInputError


def skip_quoted_text(*, sql: str, start: int, context: str = "SQL") -> int:
    """Skip past a quoted string (single, double, or backtick) starting at ``start``."""

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
    raise CompileInputError(f"{context} contains an unclosed quoted string")


def skip_line_comment(*, sql: str, start: int) -> int:
    """Skip past a ``--`` line comment starting at ``start``."""

    newline_index: int = sql.find("\n", start)
    return len(sql) if newline_index == -1 else newline_index + 1


def skip_block_comment(*, sql: str, start: int, context: str = "SQL") -> int:
    """Skip past a ``/* ... */`` block comment starting at ``start``."""

    closing_index: int = sql.find("*/", start + 2)
    if closing_index == -1:
        raise CompileInputError(f"{context} contains an unclosed block comment")
    return closing_index + 2


def find_matching_paren(*, sql: str, open_paren_index: int, context: str = "SQL") -> int:
    """Find the closing paren matching the open paren at ``open_paren_index``."""

    depth: int = 1
    index: int = open_paren_index + 1
    while index < len(sql):
        if sql.startswith("--", index):
            index = skip_line_comment(sql=sql, start=index)
            continue
        if sql.startswith("/*", index):
            index = skip_block_comment(sql=sql, start=index, context=context)
            continue
        if sql[index] in {"'", '"', "`"}:
            index = skip_quoted_text(sql=sql, start=index, context=context)
            continue
        if sql[index] == "(":
            depth += 1
        elif sql[index] == ")":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    raise CompileInputError(f"{context} contains an unclosed parenthesis")


def is_identifier_start(character: str) -> bool:
    """Check whether a character can begin an SQL identifier."""

    return character.isalpha() or character == "_"


def is_identifier_character(character: str) -> bool:
    """Check whether a character can continue an SQL identifier."""

    return character.isalnum() or character == "_"
