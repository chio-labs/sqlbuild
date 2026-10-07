"""Locate where a SQL test or scenario body omits its trailing ceremonial `SELECT 1`."""

from __future__ import annotations

from sqlbuild.compiler.discovery._helpers.sql.tests import (
    omitted_ceremonial_select_offset_impl,
)
from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax


def omitted_ceremonial_select_offset(*, sql: str, syntax: SqlLexicalSyntax) -> int | None:
    """Return the offset after a body's last top-level CTE when it ends without `SELECT 1`."""

    return omitted_ceremonial_select_offset_impl(sql=sql, syntax=syntax)
