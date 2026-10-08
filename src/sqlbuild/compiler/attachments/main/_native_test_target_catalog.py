"""Build the native SQL test target catalog once per compile for the preview compiler engine."""

from __future__ import annotations

from collections.abc import Collection

import sqlbuild._native as _native


def native_test_target_catalog(
    *,
    models: Collection[str] = (),
    sources: Collection[str] = (),
    seeds: Collection[str] = (),
    table_functions: Collection[str] = (),
    macros: Collection[str] = (),
) -> _native.SqlTestTargetCatalog:
    """Return the project's resource names as one native catalog shared by every test."""

    return _native.SqlTestTargetCatalog(
        set(models), set(sources), set(seeds), (set(table_functions), set(macros))
    )
