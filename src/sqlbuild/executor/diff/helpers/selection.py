"""Model selection helpers for diff execution."""

from __future__ import annotations

from typing import Any

from sqlbuild.executor.shared.helpers.naming import build_qualified_name


def qualified_name(model: Any) -> str:
    """Return a compiled model's relation name."""

    if model.target.qualified_name is not None:
        return model.target.qualified_name
    return build_qualified_name(
        database=model.target.database,
        schema=model.target.schema,
        name=model.target.name,
    )


def get_unique_key(model: Any) -> tuple[str, ...]:
    """Return a model's normalized unique key for row diffing."""

    raw: object | None = model.config.values.get("unique_key")
    if isinstance(raw, str) and raw:
        return (raw,)
    if isinstance(raw, list | tuple) and all(isinstance(item, str) for item in raw):
        values: tuple[str, ...] = tuple(str(item) for item in raw)
        if values:
            return values
    raise ValueError(f"model '{model.name}' requires unique_key for row diff")


def get_row_diff_exclude_columns(model: Any) -> tuple[str, ...]:
    """Return normalized row diff excluded columns."""

    raw: object | None = model.config.values.get("row_diff_exclude_columns")
    if raw is None:
        return ()
    if isinstance(raw, str):
        return (raw,)
    if isinstance(raw, list | tuple) and all(isinstance(item, str) for item in raw):
        return tuple(str(item) for item in raw)
    raise ValueError(f"model '{model.name}' row_diff_exclude_columns must be strings")


def is_disabled(model: Any) -> bool:
    """Return true when a compiled model is disabled."""

    raw: object | None = model.config.values.get("enabled")
    return isinstance(raw, bool) and not raw
