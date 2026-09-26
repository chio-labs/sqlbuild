"""Normalize a compile batch under one native GIL-release boundary."""

from typing import cast

import sqlbuild._native as _native
from sqlbuild.compiler.sql_analysis.types import NativePositionsModule


def normalize_analysis_sqls(
    *,
    sqls: tuple[str, ...],
    dialect: str | None,
    placeholders: tuple[dict[str, str] | None, ...],
) -> list[str]:
    requests: list[tuple[str, dict[str, str]]] = [
        (sql, defaults or {}) for sql, defaults in zip(sqls, placeholders, strict=True)
    ]
    return cast(NativePositionsModule, _native).normalize_analysis_sqls(
        dialect=dialect or "generic",
        requests=requests,
    )
