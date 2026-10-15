"""Stable SQLBuild-owned schema validation models."""

from __future__ import annotations

from dataclasses import dataclass

from sqlbuild._native import UnsupportedLexicalSyntaxError
from sqlbuild.compiler.sql_analysis.constants import (
    SQL_BLOCK_COMMENT_OPEN,
    SQL_ESCAPABLE_QUOTE_CHARACTERS,
    SQL_ESCAPE_CHARACTER,
    SQL_LINE_COMMENT_PREFIX,
    SQL_TRIPLE_QUOTE_LENGTH,
    SUPPORTED_SQL_LINE_COMMENT_PREFIXES,
)


@dataclass(frozen=True)
class SqlLexicalSyntax:
    """Dialect rules for where SQL quoted text and comments end."""

    backslash_escape_quotes: frozenset[str] = frozenset()
    escape_string_prefix: bool = False
    raw_string_prefix: bool = False
    triple_quoted_strings: bool = False
    nested_block_comments: bool = False
    line_comment_prefixes: frozenset[str] = frozenset({SQL_LINE_COMMENT_PREFIX})

    def __post_init__(self) -> None:
        unsupported: frozenset[str] = (
            self.line_comment_prefixes - SUPPORTED_SQL_LINE_COMMENT_PREFIXES
        )
        if unsupported:
            raise UnsupportedLexicalSyntaxError(
                f"SQL line comment prefixes {sorted(unsupported)} are not supported; SQLBuild "
                f"scans only {sorted(SUPPORTED_SQL_LINE_COMMENT_PREFIXES)}"
            )

    @property
    def cache_key(self) -> str:
        """Return a process-stable text key for these lexical rules."""

        return "|".join(
            (
                ",".join(sorted(self.backslash_escape_quotes)),
                str(self.escape_string_prefix),
                str(self.raw_string_prefix),
                str(self.triple_quoted_strings),
                str(self.nested_block_comments),
                ",".join(sorted(self.line_comment_prefixes)),
            )
        )

    @property
    def native_mapping(self) -> dict[str, object]:
        """Return these lexical rules as the mapping native scanners read."""

        return {
            "backslash_escape_quotes": sorted(self.backslash_escape_quotes),
            "escape_string_prefix": self.escape_string_prefix,
            "raw_string_prefix": self.raw_string_prefix,
            "triple_quoted_strings": self.triple_quoted_strings,
            "nested_block_comments": self.nested_block_comments,
            "line_comment_prefixes": sorted(self.line_comment_prefixes),
        }

    def reads_differently_from_generic(self, sql: str) -> bool:
        """Return whether these rules can read the SQL differently from generic SQL."""

        if SQL_ESCAPE_CHARACTER in sql and (
            self.backslash_escape_quotes or self.escape_string_prefix
        ):
            return True
        if self.triple_quoted_strings and any(
            quote * SQL_TRIPLE_QUOTE_LENGTH in sql for quote in SQL_ESCAPABLE_QUOTE_CHARACTERS
        ):
            return True
        if self.nested_block_comments and sql.count(SQL_BLOCK_COMMENT_OPEN) > 1:
            return True
        return any(
            prefix in sql
            for prefix in self.line_comment_prefixes
            if prefix != SQL_LINE_COMMENT_PREFIX
        )
