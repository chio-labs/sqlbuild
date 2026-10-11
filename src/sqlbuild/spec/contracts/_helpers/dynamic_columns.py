"""Shared matching helpers for dynamic column contract families."""

from __future__ import annotations

from functools import lru_cache

import sqlbuild._native as _native
from sqlbuild.spec.contracts.models import SchemaDynamicColumnFamily


def dynamic_family_accepts_name(*, family: SchemaDynamicColumnFamily, column_name: str) -> bool:
    """Return whether a runtime column name belongs to a declared family."""

    if family.name_pattern is None:
        return True
    return _compiled_name_pattern(family.name_pattern).matches(column_name)


def matching_dynamic_families(
    *, families: tuple[SchemaDynamicColumnFamily, ...], column_name: str
) -> tuple[SchemaDynamicColumnFamily, ...]:
    """Return every family whose optional naming constraint accepts a column."""

    return tuple(
        family
        for family in families
        if dynamic_family_accepts_name(family=family, column_name=column_name)
    )


@lru_cache(maxsize=256)
def _compiled_name_pattern(pattern: str) -> _native.NamePattern:
    return _native.NamePattern(pattern)
