"""Expected-model relationship names scanned natively for the native declaration scope."""

from __future__ import annotations

from collections.abc import Sequence

import sqlbuild._native as _native
from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax


def native_expected_model_names(
    *, sqls: Sequence[str], syntax: SqlLexicalSyntax
) -> list[tuple[str, ...] | None]:
    """Return each body's expected-model names, or None where Python must extract them."""

    if not sqls:
        return []
    try:
        names: list[list[str] | None] = _native.scope_expected_model_names(
            list(sqls), syntax.native_mapping
        )
    except (TypeError, UnicodeError):
        return [None] * len(sqls)
    return [None if model_names is None else tuple(model_names) for model_names in names]
