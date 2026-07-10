"""Model config extraction helpers for resolve modules."""

from __future__ import annotations

from datetime import date, datetime

from sqlbuild.compiler.compile.models.core import CompiledModel
from sqlbuild.compiler.planner.types import IncrementalStrategy


def get_config_str(model: CompiledModel, *, key: str) -> str | None:
    """Extract a string config value from model config."""

    raw: object | None = model.config.values.get(key)
    return raw if isinstance(raw, str) else None


def get_config_cursor_start(model: CompiledModel) -> str | None:
    """Extract cursor_start as a normalized string value."""

    raw: object | None = model.config.values.get("cursor_start")
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw.isoformat()
    if isinstance(raw, date):
        return raw.isoformat()
    if isinstance(raw, int):
        return str(raw)
    if isinstance(raw, str):
        return raw
    return None


def get_config_append_cursor_inclusive(model: CompiledModel) -> bool:
    """Return effective append cursor lower-bound inclusivity."""

    strategy: str | None = get_config_str(model, key="incremental_strategy")
    if strategy != IncrementalStrategy.APPEND:
        return True
    raw: object | None = model.config.values.get("append_cursor_inclusive")
    if isinstance(raw, bool):
        return raw
    return True
