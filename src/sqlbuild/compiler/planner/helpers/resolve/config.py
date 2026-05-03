"""Model config extraction helpers for resolve modules."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import CompiledModel


def get_config_str(model: CompiledModel, key: str) -> str | None:
    """Extract a string config value from model config."""

    raw: object | None = model.config.values.get(key)
    return raw if isinstance(raw, str) else None
