"""Expected-model relationship names scanned natively for the native declaration scope."""

from __future__ import annotations

from collections.abc import Sequence

import sqlbuild._native as _native
from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax


def native_expected_model_names(
    *, texts: Sequence[tuple[str, str]], scenario: bool, syntax: SqlLexicalSyntax
) -> list[tuple[str, ...] | str | None]:
    """Return each `(sql, file label)` body's names, Python's error, or None for Python."""

    if not texts:
        return []
    try:
        outcomes: list[tuple[str | None, list[str]] | None] = _native.scope_expected_model_names(
            list(texts), scenario, syntax.native_mapping
        )
    except (TypeError, UnicodeError):
        return [None] * len(texts)
    return [
        None if outcome is None else outcome[0] if outcome[0] is not None else tuple(outcome[1])
        for outcome in outcomes
    ]
