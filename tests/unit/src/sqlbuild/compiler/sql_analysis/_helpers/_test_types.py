from __future__ import annotations

from dataclasses import dataclass


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
