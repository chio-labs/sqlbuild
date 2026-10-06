"""Normalize analysis SQL batches under one native GIL-release boundary."""

from collections.abc import Callable, Mapping, Sequence
from typing import cast

import sqlbuild._native as _native
from sqlbuild.compiler.sql_analysis.constants import ANALYSIS_NORMALIZATION_CHUNK_SIZE
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

    normalize: Callable[..., list[str | Exception]] = (
        catalog.normalize_analysis_sqls
        if catalog is not None
        else cast(NativePositionsModule, _native).normalize_analysis_sqls
    )
    results: list[str | Exception] = []
    for start in range(0, len(requests), ANALYSIS_NORMALIZATION_CHUNK_SIZE):
        chunk: list[NativeNormalizationRequest] = [
            (sql, dict(stubs or {}), dict(placeholders or {}))
            for sql, stubs, placeholders in requests[
                start : start + ANALYSIS_NORMALIZATION_CHUNK_SIZE
            ]
        ]
        results.extend(normalize(dialect=dialect or "generic", requests=chunk))
    return results
