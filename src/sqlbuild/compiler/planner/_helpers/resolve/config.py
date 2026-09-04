"""Model config extraction helpers for resolve modules."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import CompiledModel
from sqlbuild.compiler.planner.types import IncrementalStrategy
from sqlbuild.spec.contracts.main.get_config_str import get_config_str


def get_config_append_cursor_inclusive(model: CompiledModel) -> bool:
    """Return effective append cursor lower-bound inclusivity."""

    strategy: str | None = get_config_str(values=model.config.values, key="incremental_strategy")
    if strategy != IncrementalStrategy.APPEND:
        return True
    raw: object | None = model.config.values.get("append_cursor_inclusive")
    if isinstance(raw, bool):
        return raw
    return True
