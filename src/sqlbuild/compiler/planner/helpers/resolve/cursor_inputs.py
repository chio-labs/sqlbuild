"""Cursor input helpers for planner-time SQL resolution."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import (
    CompiledModel,
    CompiledRelationTarget,
    CompileSqlReference,
)
from sqlbuild.shared.types import SqlReferenceKind


def has_model_backed_cursor_inputs(
    *,
    model: CompiledModel,
    model_targets: dict[str, CompiledRelationTarget],
    seed_targets: dict[str, CompiledRelationTarget],
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
