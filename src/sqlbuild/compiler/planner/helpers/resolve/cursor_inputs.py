"""Cursor input helpers for planner-time SQL resolution."""

from __future__ import annotations

from sqlbuild.compiler.compile.models.core import (
    CompiledModel,
    CompiledRelationDestination,
    CompileSqlReference,
)
from sqlbuild.shared.types import SqlReferenceKind


def has_model_backed_cursor_inputs(
    *,
    model: CompiledModel,
    model_targets: dict[str, CompiledRelationDestination],
    seed_targets: dict[str, CompiledRelationDestination],
    cursor_inputs: dict[str, str],
) -> bool:
    """Return whether any cursor input points at another model relation."""

    ref: CompileSqlReference
    for ref in model.references:
        if ref.ref_name not in cursor_inputs:
            continue
        if ref.ref_kind != SqlReferenceKind.REF:
            continue
        if ref.ref_name in seed_targets:
            continue
        if ref.ref_name in model_targets:
            return True
    return False
