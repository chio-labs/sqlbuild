"""Native SQL code scanners for the scanning tests."""

from __future__ import annotations

import sqlbuild._native as _native
from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax


def generic_scanner(*, sql: str, context: str = "SQL") -> _native.SqlCodeScanner:
    """A native scanner over `sql` under the generic compiler rules."""

    return _native.SqlCodeScanner(sql, None, context)


def dialect_scanner(*, sql: str, syntax: SqlLexicalSyntax) -> _native.SqlCodeScanner:
    """A native scanner over `sql` under one dialect's lexical rules."""

    return _native.SqlCodeScanner(sql, syntax.native_mapping, "SQL")
