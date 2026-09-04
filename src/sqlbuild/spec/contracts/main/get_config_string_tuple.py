"""Public typed string-sequence config extraction."""

from __future__ import annotations

from collections.abc import Mapping

from sqlbuild.spec.contracts._helpers.config_values import _get_config_string_tuple


def get_config_string_tuple(*, values: Mapping[str, object], key: str) -> tuple[str, ...] | None:
    """Return an authored sequence of strings, or None when absent."""

    return _get_config_string_tuple(values=values, key=key)
