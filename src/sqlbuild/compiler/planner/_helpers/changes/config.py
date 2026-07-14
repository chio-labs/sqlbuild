"""Model config extraction helpers for change detection."""

from __future__ import annotations

from sqlbuild.compiler.compile.models.core import CompiledModel


def get_config_str(*, model: CompiledModel, key: str) -> str | None:
    """Extract a string config value from model config."""

    raw: object | None = model.config.values.get(key)
    return raw if isinstance(raw, str) else None


def get_config_dict(*, model: CompiledModel, key: str) -> dict[str, str]:
    """Extract a dict config value from model config."""

    raw: object | None = model.config.values.get(key)
    if not isinstance(raw, dict):
        return {}
    return {k: v for k, v in raw.items() if isinstance(k, str) and isinstance(v, str)}
