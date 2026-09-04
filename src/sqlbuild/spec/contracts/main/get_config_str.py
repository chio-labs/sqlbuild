"""Public typed string config extraction."""

from __future__ import annotations

from collections.abc import Mapping

from sqlbuild.spec.contracts._helpers.config_values import _get_config_str


def get_config_str(*, values: Mapping[str, object], key: str) -> str | None:
    """Return an authored string, preserving a present empty string."""

    return _get_config_str(values=values, key=key)
