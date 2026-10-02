from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax


@dataclass(frozen=True)
class SkipQuotedTextSuccessTestCase:
    """Successful quoted-text scan case."""

    description: str
    quoted_sql: str
    expected_end: int


@dataclass(frozen=True)
class SkipQuotedTextErrorTestCase:
    """Invalid quoted-text scan case."""

    description: str
    sql: str
    context: str
    expected_error: str


@dataclass(frozen=True)
class IterCodePositionsTestCase:
    """Code-position scan case."""

    description: str
    sql: str
    expected_positions: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class DialectQuotedTextSuccessTestCase:
    """Successful dialect-aware quoted-text scan case."""

    description: str
    syntax: SqlLexicalSyntax
    sql: str
    start: int
    expected_end: int


@dataclass(frozen=True)
class DialectQuotedTextErrorTestCase:
    """Dialect-aware quoted-text scan that cannot find the end of the text."""

    description: str
    syntax: SqlLexicalSyntax
    sql: str
    expected_error: str


@dataclass(frozen=True)
class DialectNonCodeSuccessTestCase:
    """Dialect-aware quoted-text or comment scan case."""

    description: str
    syntax: SqlLexicalSyntax
    sql: str
    expected_end: int | None


@dataclass(frozen=True)
class DialectNonCodeErrorTestCase:
    """Dialect-aware comment scan that cannot find the end of the comment."""

    description: str
    syntax: SqlLexicalSyntax
    sql: str
    expected_error: str


@dataclass(frozen=True)
class RequiresDialectScanTestCase:
    """Detection of SQL a dialect lexes differently from generic SQL."""

    description: str
    syntax: SqlLexicalSyntax
    sql: str
    expected_reads_differently: bool


@dataclass(frozen=True)
class DialectMatchingParenTestCase:
    """Dialect-aware parenthesis matching case."""

    description: str
    syntax: SqlLexicalSyntax | None
    sql: str
    expected_index: int
