"""Expected-model relationship names scanned natively for the native declaration scope."""

from __future__ import annotations

from collections.abc import Sequence

import sqlbuild._native as _native
from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax


def native_expected_model_names(
    *, texts: Sequence[tuple[str, str]], scenario: bool, syntax: SqlLexicalSyntax
) -> list[tuple[str, ...] | str]:
    """Return each `(sql, file label)` body's names or its error."""

    if not texts:
        return []
    outcomes: list[tuple[str | None, list[str]]] = _native.scope_expected_model_names(
        list(texts), scenario, syntax.native_mapping
    )
    return [outcome[0] if outcome[0] is not None else tuple(outcome[1]) for outcome in outcomes]
