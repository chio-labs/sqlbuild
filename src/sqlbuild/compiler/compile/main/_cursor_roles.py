"""Resolve authored cursor input fields into their explicit roles."""

from __future__ import annotations

from typing import Any

from sqlbuild.compiler.compile.constants import (
    CURSOR_FILTER_INPUTS_CONFIG_KEY,
    CURSOR_INPUTS_CONFIG_KEY,
    CURSOR_WATERMARK_INPUTS_CONFIG_KEY,
)
from sqlbuild.compiler.compile.models import CompiledModel, CursorInputRoles


def resolve_cursor_input_roles(*, model: CompiledModel) -> CursorInputRoles:
    """Resolve authored cursor input fields into explicit effective roles."""

    explicit: object | None = model.config.values.get(CURSOR_FILTER_INPUTS_CONFIG_KEY)
    legacy: object | None = model.config.values.get(CURSOR_INPUTS_CONFIG_KEY)
    authored: object | None = explicit if explicit is not None else legacy
    filter_inputs: dict[str, str]
    if isinstance(authored, dict):
        filter_inputs = _string_map(authored)
    else:
        cursor: object | None = model.config.values.get("cursor")
        filter_inputs = (
            {reference.ref_name: cursor for reference in model.references}
            if isinstance(cursor, str)
            else {}
        )
    explicit_watermarks: object | None = model.config.values.get(CURSOR_WATERMARK_INPUTS_CONFIG_KEY)
    watermark_inputs: dict[str, str] = (
        _string_map(explicit_watermarks) if isinstance(explicit_watermarks, dict) else filter_inputs
    )
    uses_legacy_alias: bool = CURSOR_INPUTS_CONFIG_KEY in model.config.values
    filter_field: str = (
        CURSOR_INPUTS_CONFIG_KEY if uses_legacy_alias else CURSOR_FILTER_INPUTS_CONFIG_KEY
    )
    watermark_field: str = (
        CURSOR_WATERMARK_INPUTS_CONFIG_KEY
        if CURSOR_WATERMARK_INPUTS_CONFIG_KEY in model.config.values
        else filter_field
    )
    return CursorInputRoles(
        filter_inputs=filter_inputs,
        watermark_inputs=watermark_inputs,
        filter_field=filter_field,
        watermark_field=watermark_field,
        uses_legacy_alias=uses_legacy_alias,
    )


def _string_map(value: dict[Any, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    key: object
    item: object
    for key, item in value.items():
        if isinstance(key, str) and isinstance(item, str):
            result[key] = item
    return result
