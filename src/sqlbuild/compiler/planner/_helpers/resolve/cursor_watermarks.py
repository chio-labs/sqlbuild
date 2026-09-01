"""Cursor input helpers for planner-time SQL resolution."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import CompiledModel, CompiledRelationLocation


def has_model_backed_cursor_watermarks(
    *,
    model: CompiledModel,
    model_locations: dict[str, CompiledRelationLocation],
    seed_locations: dict[str, CompiledRelationLocation],
    cursor_watermark_inputs: dict[str, str],
) -> bool:
    """Return whether any cursor input points at another model relation."""

    _ = model
    input_name: str
    for input_name in cursor_watermark_inputs:
        if input_name in seed_locations:
            continue
        if input_name in model_locations:
            return True
    return False
