"""Stable SQLBuild-owned schema validation models."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from sqlbuild.compiler.sql_analysis.constants import (
    SQL_BLOCK_COMMENT_OPEN,
    SQL_ESCAPABLE_QUOTE_CHARACTERS,
    SQL_ESCAPE_CHARACTER,
    SQL_LINE_COMMENT_PREFIX,
    SQL_TRIPLE_QUOTE_LENGTH,
)


@dataclass(frozen=True)
class SqlBindingDiagnostic:
    """One native binding error or non-blocking runtime-conversion warning."""

    code: str
    message: str
    line: int | None = None
    column: int | None = None
    start: int | None = None
    end: int | None = None
    severity: str = "error"


@dataclass(frozen=True)
class SqlBindingResult:
    """Stable result of schema-aware semantic SQL validation."""

    diagnostics: tuple[SqlBindingDiagnostic, ...] = ()


@dataclass(frozen=True)
class SqlSchemaValidationRequest:
    """One expanded SQL query and its complete relation schemas."""

    sql: str
    dialect: str | None
    schema: Mapping[str, Mapping[str, str]]
    known_functions: tuple[str, ...] = ()
    known_types: tuple[str, ...] = ()
    quoted_identifiers_ignore_case: bool = False
    catalog: Any | None = field(default=None, repr=False, compare=False)


@dataclass(frozen=True)
class SqlLexicalSyntax:
    """Dialect rules for where SQL quoted text and comments end."""

    backslash_escape_quotes: frozenset[str] = frozenset()
    escape_string_prefix: bool = False
    raw_string_prefix: bool = False
    triple_quoted_strings: bool = False
    nested_block_comments: bool = False
    line_comment_prefixes: frozenset[str] = frozenset({SQL_LINE_COMMENT_PREFIX})

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
