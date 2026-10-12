"""Public entrypoint for declaration placement validation."""

from __future__ import annotations

import sqlbuild._native as _native
from sqlbuild.compiler.scopes.models import ScopeIndex, UsageRecord


def get_placement_validated_scope_index(
    *,
    index: ScopeIndex,
    enforce_placement: bool = True,
    compile_usages: tuple[UsageRecord, ...] | None = None,
) -> ScopeIndex:
    """Return complete usage and placement diagnostics, merging any collected compile usages."""

    return _native.scope_placement_validated_index(index, enforce_placement, compile_usages)
