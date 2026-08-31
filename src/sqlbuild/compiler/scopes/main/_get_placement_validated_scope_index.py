"""Public entrypoint for declaration placement validation."""

from __future__ import annotations

from sqlbuild.compiler.scopes._helpers.placement import build_placement_validated_index
from sqlbuild.compiler.scopes.models import ScopeIndex


def get_placement_validated_scope_index(
    *, index: ScopeIndex, enforce_placement: bool = True
) -> ScopeIndex:
    """Return complete deterministic usage and placement diagnostics."""

    return build_placement_validated_index(index=index, enforce_placement=enforce_placement)
