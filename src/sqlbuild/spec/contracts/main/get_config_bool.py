"""Public typed boolean config extraction."""

from __future__ import annotations

from collections.abc import Mapping

from sqlbuild.spec.contracts._helpers.config_values import _get_config_bool


def get_config_bool(*, values: Mapping[str, object], key: str) -> bool | None:
    """Return an authored boolean, or None only when the key is absent."""

    return _get_config_bool(values=values, key=key)
