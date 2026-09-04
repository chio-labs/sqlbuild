"""Public typed integer config extraction."""

from __future__ import annotations

from collections.abc import Mapping

from sqlbuild.spec.contracts._helpers.config_values import _get_config_int


def get_config_int(*, values: Mapping[str, object], key: str) -> int | None:
    """Return an authored integer, excluding booleans, or None when absent."""

    return _get_config_int(values=values, key=key)
