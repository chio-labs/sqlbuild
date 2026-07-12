"""Public executable SQL reference validation entry."""

from __future__ import annotations

from sqlbuild.compiler.references.helpers.resolution import (
    assert_no_unresolved_sql_markers as _assert_no_unresolved_sql_markers,
)


def assert_no_unresolved_sql_markers(*, sql: str, context: str) -> None:
    """Fail fast if executable SQL still contains unresolved reference markers."""

    return _assert_no_unresolved_sql_markers(sql=sql, context=context)
