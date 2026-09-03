"""Resolve authored cursor input fields into their explicit roles."""

from __future__ import annotations

from typing import Any, cast

from sqlbuild.compiler.compile.constants import CURSOR_INPUTS_CONFIG_KEY
from sqlbuild.compiler.compile.models import CompiledModel, CursorInputRoles
from sqlbuild.compiler.planner.types import CursorInputRole, MicrobatchStrategy


def resolve_cursor_input_roles(*, model: CompiledModel) -> CursorInputRoles:
    """Resolve authored cursor input fields into explicit effective roles."""

    authored: object | None = model.config.values.get(CURSOR_INPUTS_CONFIG_KEY)
    strategy: object | None = model.config.values.get("microbatch_strategy")
    filter_inputs: dict[str, str] = {}
    watermark_inputs: dict[str, str] = {}
    if isinstance(authored, dict) and strategy == MicrobatchStrategy.WATERMARK:
        for relation, block in authored.items():
            if not isinstance(relation, str) or not isinstance(block, dict):
                continue
            typed_block: dict[object, object] = cast(dict[object, object], block)
            column: object | None = typed_block.get("column")
            roles: object | None = typed_block.get("roles")
            if not isinstance(column, str) or not isinstance(roles, list):
                continue
            if CursorInputRole.FILTER in roles:
                filter_inputs[relation] = column
            if CursorInputRole.WATERMARK in roles:
                watermark_inputs[relation] = column
    elif isinstance(authored, dict):
        filter_inputs = _string_map(authored)
        if strategy != MicrobatchStrategy.ROLLING_WINDOW:
            watermark_inputs = filter_inputs
    else:
        cursor: object | None = model.config.values.get("cursor")
        filter_inputs = (
            {reference.ref_name: cursor for reference in model.references}
            if isinstance(cursor, str)
            else {}
        )
        if strategy != MicrobatchStrategy.ROLLING_WINDOW:
            watermark_inputs = filter_inputs
    return CursorInputRoles(
        filter_inputs=filter_inputs,
        watermark_inputs=watermark_inputs,
        filter_field=CURSOR_INPUTS_CONFIG_KEY,
        watermark_field=CURSOR_INPUTS_CONFIG_KEY,
        uses_legacy_alias=False,
    )


def _string_map(value: dict[Any, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    key: object
    item: object
    for key, item in value.items():
        if isinstance(key, str) and isinstance(item, str):
            result[key] = item
    return result
