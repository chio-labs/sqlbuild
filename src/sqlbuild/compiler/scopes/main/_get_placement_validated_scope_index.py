"""Public entrypoint for declaration placement validation."""

from __future__ import annotations

from sqlbuild.compiler.scopes._helpers.placement import (
    build_placement_validated_index,
    merged_usage_index,
)
from sqlbuild.compiler.scopes.models import ScopeIndex, UsageRecord


def get_placement_validated_scope_index(
    *,
    index: ScopeIndex,
    enforce_placement: bool = True,
    compile_usages: tuple[UsageRecord, ...] | None = None,
) -> ScopeIndex:
    """Return complete usage and placement diagnostics, merging any collected compile usages."""

    if compile_usages is not None:
        index = merged_usage_index(index=index, collected=compile_usages)
    return build_placement_validated_index(index=index, enforce_placement=enforce_placement)
