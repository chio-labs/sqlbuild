"""Typed extraction from raw authored configuration mappings."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from typing import Never, cast

from sqlbuild.spec.contracts.exceptions import ConfigValueTypeError


def _get_config_str(*, values: Mapping[str, object], key: str) -> str | None:
    """Return an authored string, preserving a present empty string."""

    value: object | None = values.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        _raise_wrong_type(key=key, expected="a string", value=value)
    return value


def _get_config_bool(*, values: Mapping[str, object], key: str) -> bool | None:
    """Return an authored boolean, or None when the key is absent or None."""

    value: object | None = values.get(key)
    if value is None:
        return None
    if not isinstance(value, bool):
        _raise_wrong_type(key=key, expected="a boolean", value=value)
    return value


def _get_config_string_tuple(*, values: Mapping[str, object], key: str) -> tuple[str, ...] | None:
    """Return an authored sequence of strings, or None when absent or None."""

    value: object | None = values.get(key)
    if value is None:
        return None
    if not isinstance(value, list | tuple) or not all(isinstance(item, str) for item in value):
        _raise_wrong_type(key=key, expected="a list or tuple of strings", value=value)
    return cast(tuple[str, ...], tuple(value))


def _get_config_int(*, values: Mapping[str, object], key: str) -> int | None:
    """Return an authored integer, excluding booleans, or None when absent or None."""

    value: object | None = values.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        _raise_wrong_type(key=key, expected="an integer", value=value)
    return value


def _get_config_cursor_bound(*, values: Mapping[str, object], key: str) -> str | None:
    """Return a cursor bound normalized to text from its supported authored scalar types."""

    value: object | None = values.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, str | int | date | datetime):
        _raise_wrong_type(
            key=key,
            expected="a string, integer, date, or datetime",
            value=value,
        )
    return value.isoformat() if isinstance(value, date | datetime) else str(value)


def _raise_wrong_type(*, key: str, expected: str, value: object | None) -> Never:
    raise ConfigValueTypeError(key=key, expected=expected, actual_type=type(value))
