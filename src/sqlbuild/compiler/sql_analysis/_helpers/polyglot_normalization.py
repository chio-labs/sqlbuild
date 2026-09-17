"""Dialect compatibility normalization for Polyglot analysis input."""

from __future__ import annotations

import re

from sqlbuild.compiler.sql_analysis._helpers.scanning import (
    skip_block_comment_impl,
    skip_line_comment_impl,
    skip_quoted_text_impl,
)
from sqlbuild.compiler.sql_analysis.constants import (
    SNOWFLAKE_DIALECT_NAME,
    SQL_CLOSE_BRACKET,
    SQL_DOLLAR_QUOTE_DELIMITER,
    SQL_ESCAPE_CHARACTER,
    SQL_OPEN_BRACKET,
    SQL_QUOTE_CHARACTERS,
    SQL_STRING_QUOTE_CHARACTER,
)

_IDENTIFIER: str = r'(?:[A-Za-z_][A-Za-z0-9_$]*|"(?:""|[^"])+")'
_VARIANT_PATH_SUFFIX: re.Pattern[str] = re.compile(
    rf"(?P<base>{_IDENTIFIER}(?:\.{_IDENTIFIER})*:{_IDENTIFIER}"
    rf"(?:(?::|\.){_IDENTIFIER})*)$"
)
_SIMPLE_BRACKET_KEY: re.Pattern[str] = re.compile(rf"\s*(?:{_IDENTIFIER}|[0-9]+|'(?:''|[^'])*')\s*")
_SCAN_SPECIAL: re.Pattern[str] = re.compile(r"[-/$'\"`\[]")


def normalize_sql_for_polyglot_impl(*, sql: str, dialect: str | None) -> str:
    """Return analysis-equivalent SQL for Polyglot's supported dialect surface."""

    if dialect is None or dialect.casefold() != SNOWFLAKE_DIALECT_NAME:
        return sql
    replacements: list[tuple[int, int, str]] = []
    index: int = 0
    while index < len(sql):
        special: re.Match[str] | None = _SCAN_SPECIAL.search(sql, index)
        if special is None:
            break
        index = special.start()
        if sql.startswith("--", index):
            index = skip_line_comment_impl(sql=sql, start=index)
            continue
        if sql.startswith("/*", index):
            index = skip_block_comment_impl(
                sql=sql,
                start=index,
                context="Snowflake SQL analysis",
            )
            continue
        if sql.startswith(SQL_DOLLAR_QUOTE_DELIMITER, index):
            index = _skip_dollar_quoted_text(sql=sql, start=index)
            continue
        if sql[index] in SQL_QUOTE_CHARACTERS:
            index = _skip_snowflake_quoted_text(sql=sql, start=index)
            continue
        close_bracket: int | None = _matching_bracket(sql=sql, open_bracket=index)
        if close_bracket is None:
            index += 1
            continue
        key_sql: str = sql[index + 1 : close_bracket]
        normalized_key: str = normalize_sql_for_polyglot_impl(sql=key_sql, dialect=dialect)
        base_end: int = _trailing_trivia_start(sql=sql, end=index)
        base_match: re.Match[str] | None = _VARIANT_PATH_SUFFIX.search(sql[:base_end])
        if base_match is not None and _SIMPLE_BRACKET_KEY.fullmatch(key_sql) is None:
            base_sql: str = base_match.group("base")
            trivia: str = sql[base_end:index]
            replacements.append(
                (
                    base_match.start("base"),
                    close_bracket + 1,
                    f"GET({base_sql}{trivia}, {normalized_key})",
                )
            )
        elif normalized_key != key_sql:
            replacements.append((index + 1, close_bracket, normalized_key))
        index = close_bracket + 1
    normalized: str = sql
    for start, end, replacement in reversed(replacements):
        normalized = f"{normalized[:start]}{replacement}{normalized[end:]}"
    return normalized


def _matching_bracket(*, sql: str, open_bracket: int) -> int | None:
    depth: int = 1
    index: int = open_bracket + 1
    while index < len(sql):
        if sql.startswith("--", index):
            index = skip_line_comment_impl(sql=sql, start=index)
            continue
        if sql.startswith("/*", index):
            index = skip_block_comment_impl(
                sql=sql,
                start=index,
                context="Snowflake SQL analysis",
            )
            continue
        if sql.startswith(SQL_DOLLAR_QUOTE_DELIMITER, index):
            index = _skip_dollar_quoted_text(sql=sql, start=index)
            continue
        if sql[index] in SQL_QUOTE_CHARACTERS:
            index = _skip_snowflake_quoted_text(sql=sql, start=index)
            continue
        if sql[index] == SQL_OPEN_BRACKET:
            depth += 1
        elif sql[index] == SQL_CLOSE_BRACKET:
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return None


def _skip_snowflake_quoted_text(*, sql: str, start: int) -> int:
    if sql[start] != SQL_STRING_QUOTE_CHARACTER:
        return skip_quoted_text_impl(sql=sql, start=start, context="Snowflake SQL analysis")
    index: int = start + 1
    while index < len(sql):
        if sql[index] == SQL_ESCAPE_CHARACTER:
            index += 2
            continue
        if sql[index] == SQL_STRING_QUOTE_CHARACTER:
            if index + 1 < len(sql) and sql[index + 1] == SQL_STRING_QUOTE_CHARACTER:
                index += 2
                continue
            return index + 1
        index += 1
    return len(sql)


def _skip_dollar_quoted_text(*, sql: str, start: int) -> int:
    closing: int = sql.find(SQL_DOLLAR_QUOTE_DELIMITER, start + len(SQL_DOLLAR_QUOTE_DELIMITER))
    return len(sql) if closing == -1 else closing + len(SQL_DOLLAR_QUOTE_DELIMITER)


def _trailing_trivia_start(*, sql: str, end: int) -> int:
    current: int = end
    while True:
        trimmed: int = current
        while trimmed > 0 and sql[trimmed - 1].isspace():
            trimmed -= 1
        if not sql[:trimmed].endswith("*/"):
            return trimmed
        opening: int = sql.rfind("/*", 0, trimmed - 2)
        if opening == -1:
            return trimmed
        current = opening
