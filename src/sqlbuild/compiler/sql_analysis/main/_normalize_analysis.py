"""Normalize analysis SQL using native offset-preserving transformations."""

from typing import cast

import sqlbuild._native as _native
from sqlbuild.compiler.sql_analysis.types import NativePositionsModule


def normalize_analysis_sql(
    *,
    sql: str,
    dialect: str | None,
    stubs: dict[str, str] | None = None,
    placeholders: dict[str, str] | None = None,
) -> str:
    return cast(NativePositionsModule, _native).normalize_analysis_sql(
        {
            "sql": sql,
            "dialect": dialect or "generic",
            "stubs": stubs or {},
            "placeholders": placeholders or {},
        }
    )
