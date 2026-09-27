"""Character-level SQL scanning implementations."""

from __future__ import annotations

import re
from collections.abc import Iterator

from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.sql_analysis.constants import (
    SQL_CLOSE_PARENTHESIS,
    SQL_DOLLAR_QUOTE_CHARACTER,
    SQL_ESCAPABLE_QUOTE_CHARACTERS,
    SQL_IDENTIFIER_PREFIX,
    SQL_OPEN_PARENTHESIS,
    SQL_TEXT_START_CHARACTERS,
)

_PAREN_SCAN_SPECIAL: re.Pattern[str] = re.compile(r"[-/'\"`$()]")
_DOLLAR_QUOTE_DELIMITER: re.Pattern[str] = re.compile(r"\$(?:[A-Za-z_][A-Za-z0-9_]*)?\$")


def skip_quoted_text_impl(*, sql: str, start: int, context: str = "SQL") -> int:
    """Skip quoted text at the position, consuming a non-opening ``$`` as one code character."""

    end: int | None = quoted_text_end_impl(sql=sql, start=start, context=context)
    return start + 1 if end is None else end


def quoted_text_end_impl(*, sql: str, start: int, context: str = "SQL") -> int | None:
    """Return the end of quoted or dollar-quoted text starting at the position, if any."""

    quote_character: str = sql[start]
    if quote_character == SQL_DOLLAR_QUOTE_CHARACTER:
        return _dollar_quoted_text_end(sql=sql, start=start, context=context)
    index: int = start + 1
    while True:
        index = sql.find(quote_character, index)
        if index == -1:
            raise CompileInputError(f"{context} contains an unclosed quoted string")
        if (
            quote_character in SQL_ESCAPABLE_QUOTE_CHARACTERS
            and index + 1 < len(sql)
            and sql[index + 1] == quote_character
        ):
            index += 2
            continue
        return index + 1


def _dollar_quoted_text_end(*, sql: str, start: int, context: str) -> int | None:
    delimiter: re.Match[str] | None = _DOLLAR_QUOTE_DELIMITER.match(sql, start)
    if delimiter is None or (start > 0 and _continues_dollar_word(sql[start - 1])):
        return None
    closing_index: int = sql.find(delimiter.group(), delimiter.end())
    if closing_index == -1:
        raise CompileInputError(f"{context} contains an unclosed quoted string")
    return closing_index + len(delimiter.group())


def _continues_dollar_word(character: str) -> bool:
    return (
        not character.isascii()
        or character.isalnum()
        or character in {SQL_IDENTIFIER_PREFIX, SQL_DOLLAR_QUOTE_CHARACTER}
    )


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
        special: re.Match[str] | None = _PAREN_SCAN_SPECIAL.search(sql, index)
        if special is None:
            break
        index = special.start()
        non_code_end: int | None = _non_code_end(sql=sql, index=index, context=context)
        if non_code_end is not None:
            index = non_code_end
            continue
        if sql[index] == SQL_OPEN_PARENTHESIS:
            depth += 1
        elif sql[index] == SQL_CLOSE_PARENTHESIS:
            depth -= 1
            if depth == 0:
                return index
        index += 1
    raise CompileInputError(f"{context} contains an unclosed parenthesis")


def iter_code_positions_impl(*, sql: str, context: str = "SQL") -> Iterator[tuple[int, int]]:
    """Yield code offsets outside comments, quotes, and parentheses with their nesting depth."""

    depth: int = 0
    index: int = 0
    while index < len(sql):
        non_code_end: int | None = _non_code_end(sql=sql, index=index, context=context)
        if non_code_end is not None:
            index = non_code_end
            continue
        character: str = sql[index]
        if character == SQL_OPEN_PARENTHESIS:
            depth += 1
        elif character == SQL_CLOSE_PARENTHESIS:
            depth -= 1
        else:
            yield index, depth
        index += 1


def _non_code_end(*, sql: str, index: int, context: str) -> int | None:
    if sql.startswith("--", index):
        return skip_line_comment_impl(sql=sql, start=index)
    if sql.startswith("/*", index):
        return skip_block_comment_impl(sql=sql, start=index, context=context)
    if sql[index] in SQL_TEXT_START_CHARACTERS:
        return quoted_text_end_impl(sql=sql, start=index, context=context)
    return None


def is_identifier_start_impl(character: str) -> bool:
    """Return whether a character can begin an SQL identifier."""

    return character.isalpha() or character == SQL_IDENTIFIER_PREFIX


def is_identifier_character_impl(character: str) -> bool:
    """Return whether a character can continue an SQL identifier."""

    return character.isalnum() or character == SQL_IDENTIFIER_PREFIX
