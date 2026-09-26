"""Public dialect compatibility normalization for Polyglot analysis input."""

from __future__ import annotations

from typing import cast

import sqlbuild._native as _native
from sqlbuild.compiler.sql_analysis.types import NativePositionsModule


def normalize_sql_for_polyglot(*, sql: str, dialect: str | None) -> str:
    """Return analysis-equivalent SQL for Polyglot's supported dialect surface."""

    return cast(NativePositionsModule, _native).normalize_dialect_sql(
        sql=sql, dialect=dialect or "generic"
    )
