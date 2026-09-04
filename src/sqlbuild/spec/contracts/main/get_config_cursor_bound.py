"""Public cursor-bound config extraction."""

from __future__ import annotations

from collections.abc import Mapping

from sqlbuild.spec.contracts._helpers.config_values import _get_config_cursor_bound


def get_config_cursor_bound(*, values: Mapping[str, object], key: str) -> str | None:
    """Return a cursor bound normalized from its supported authored scalar types."""

    return _get_config_cursor_bound(values=values, key=key)
