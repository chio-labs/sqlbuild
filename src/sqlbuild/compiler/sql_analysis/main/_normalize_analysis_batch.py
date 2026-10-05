"""Normalize analysis SQL batches under one native GIL-release boundary."""

from collections.abc import Mapping, Sequence
from typing import cast

import sqlbuild._native as _native
from sqlbuild.compiler.sql_analysis.types import (
    NativeNormalizationRequest,
    NativePositionsModule,
    NativeProjectCatalog,
)


def normalize_analysis_sql_results(
    *,
    dialect: str | None,
    requests: Sequence[tuple[str, Mapping[str, str] | None, Mapping[str, str] | None]],
    catalog: NativeProjectCatalog | None,
) -> list[str | Exception]:
    """Normalize `(sql, stubs, placeholders)` in order, keeping each failure in its place."""

    if not requests:
        return []
    payload: list[NativeNormalizationRequest] = [
        (sql, dict(stubs or {}), dict(placeholders or {})) for sql, stubs, placeholders in requests
    ]
    if catalog is not None:
        return catalog.normalize_analysis_sqls(dialect=dialect or "generic", requests=payload)
    return cast(NativePositionsModule, _native).normalize_analysis_sqls(
        dialect=dialect or "generic", requests=payload
    )
