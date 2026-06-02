"""Model selection helpers for diff execution."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.executor.shared.exceptions import ExecutorInputError
from sqlbuild.shared.helpers.naming import resolve_destination_qualified_name


def qualified_name(*, adapter: BaseAdapter, model: Any) -> str:
    """Return a compiled model's relation name."""

    return resolve_destination_qualified_name(adapter=adapter, target=model.destination)


def get_unique_key(model: Any) -> tuple[str, ...]:
    """Return a model's normalized unique key for row diffing."""

    raw: object | None = model.config.values.get("unique_key")
    if isinstance(raw, str) and raw:
        return (raw,)
    if isinstance(raw, list | tuple) and all(isinstance(item, str) for item in raw):
        values: tuple[str, ...] = tuple(str(item) for item in raw)
        if values:
            return values
    raise ExecutorInputError(f"model '{model.name}' requires unique_key for row diff", code="X201")


def get_row_diff_exclude_columns(model: Any) -> tuple[str, ...]:
    """Return normalized row diff excluded columns."""

    raw: object | None = model.config.values.get("row_diff_exclude_columns")
    if raw is None:
        return ()
    if isinstance(raw, str):
        return (raw,)
    if isinstance(raw, list | tuple) and all(isinstance(item, str) for item in raw):
        return tuple(str(item) for item in raw)
    raise ExecutorInputError(
        f"model '{model.name}' row_diff_exclude_columns must be strings",
        code="X202",
    )


def is_disabled(model: Any) -> bool:
    """Return true when a compiled model is disabled."""

    raw: object | None = model.config.values.get("enabled")
    return isinstance(raw, bool) and not raw
