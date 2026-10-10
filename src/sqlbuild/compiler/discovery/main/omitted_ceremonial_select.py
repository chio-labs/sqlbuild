"""Locate where a SQL test or scenario body omits its trailing ceremonial `SELECT 1`."""

from __future__ import annotations

import sqlbuild._native as _native
from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax


def omitted_ceremonial_select_offset(*, sql: str, syntax: SqlLexicalSyntax) -> int | None:
    """Return the offset after a body's last top-level CTE when it ends without `SELECT 1`."""

    return _native.omitted_ceremonial_select(sql, syntax.native_mapping)
