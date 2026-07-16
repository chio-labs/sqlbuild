"""Character-level SQL scanning implementations."""

from __future__ import annotations

from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.sql_analysis.constants import (
    SQL_CLOSE_PARENTHESIS,
    SQL_ESCAPABLE_QUOTE_CHARACTERS,
    SQL_IDENTIFIER_PREFIX,
    SQL_OPEN_PARENTHESIS,
    SQL_QUOTE_CHARACTERS,
)


def skip_quoted_text_impl(*, sql: str, start: int, context: str = "SQL") -> int:
    """Skip past quoted SQL text starting at the supplied position."""

    quote_character: str = sql[start]
    index: int = start + 1
    while index < len(sql):
        if sql[index] == quote_character:
            if (
                quote_character in SQL_ESCAPABLE_QUOTE_CHARACTERS
                and index + 1 < len(sql)
                and sql[index + 1] == quote_character
            ):
                index += 2
                continue
            return index + 1
        index += 1
    raise CompileInputError(f"{context} contains an unclosed quoted string")


def skip_line_comment_impl(*, sql: str, start: int) -> int:
    """Skip past an SQL line comment."""

    newline_index: int = sql.find("\n", start)
    return len(sql) if newline_index == -1 else newline_index + 1


def skip_block_comment_impl(*, sql: str, start: int, context: str = "SQL") -> int:
    """Skip past an SQL block comment."""

    closing_index: int = sql.find("*/", start + 2)
    if closing_index == -1:
        raise CompileInputError(f"{context} contains an unclosed block comment")
    return closing_index + 2


def find_matching_paren_impl(*, sql: str, open_paren_index: int, context: str = "SQL") -> int:
    """Find the closing parenthesis matching an opening parenthesis."""

    depth: int = 1
    index: int = open_paren_index + 1
    while index < len(sql):
        if sql.startswith("--", index):
            index = skip_line_comment_impl(sql=sql, start=index)
            continue
        if sql.startswith("/*", index):
            index = skip_block_comment_impl(sql=sql, start=index, context=context)
            continue
        if sql[index] in SQL_QUOTE_CHARACTERS:
            index = skip_quoted_text_impl(sql=sql, start=index, context=context)
            continue
        if sql[index] == SQL_OPEN_PARENTHESIS:
            depth += 1
        elif sql[index] == SQL_CLOSE_PARENTHESIS:
            depth -= 1
            if depth == 0:
                return index
        index += 1
    raise CompileInputError(f"{context} contains an unclosed parenthesis")


def is_identifier_start_impl(character: str) -> bool:
    """Return whether a character can begin an SQL identifier."""

    return character.isalpha() or character == SQL_IDENTIFIER_PREFIX


def is_identifier_character_impl(character: str) -> bool:
    """Return whether a character can continue an SQL identifier."""

    return character.isalnum() or character == SQL_IDENTIFIER_PREFIX
