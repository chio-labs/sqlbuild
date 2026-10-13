"""Model config extraction helpers for resolve modules."""

from __future__ import annotations

from sqlbuild._native import get_config_str
from sqlbuild.compiler.compile.types import CompiledModelView
from sqlbuild.compiler.planner.types import IncrementalStrategy


def get_config_append_cursor_inclusive(model: CompiledModelView) -> bool:
    """Return effective append cursor lower-bound inclusivity."""

    strategy: str | None = get_config_str(values=model.config.values, key="incremental_strategy")
    if strategy != IncrementalStrategy.APPEND:
        return True
    raw: object | None = model.config.values.get("append_cursor_inclusive")
    if isinstance(raw, bool):
        return raw
    return True
