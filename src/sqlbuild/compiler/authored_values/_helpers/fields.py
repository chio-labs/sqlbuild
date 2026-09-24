"""Authored configuration value validation implementations."""

from __future__ import annotations

from pathlib import Path
from typing import cast


def require_non_empty_string_impl(
    *,
    entry: dict[str, object],
    key: str,
    file_path: Path,
    label: str,
    error_class: type[Exception],
) -> str:
    """Extract a required non-empty string from a mapping."""

    raw_value: object | None = entry.get(key)
    if not isinstance(raw_value, str) or not raw_value.strip():
        raise error_class(f"{file_path} {label} must define non-empty string '{key}'")
    return raw_value


def optional_non_empty_string_impl(
    *,
    entry: dict[str, object],
    key: str,
    file_path: Path,
    label: str,
    error_class: type[Exception],
) -> str | None:
    """Extract an optional non-empty string from a mapping."""

    return optional_named_string_impl(
        raw_value=entry.get(key),
        file_path=file_path,
        label=label,
        key=key,
        error_class=error_class,
    )


def optional_named_string_impl(
    *,
    raw_value: object | None,
    file_path: Path,
    label: str,
    key: str,
    error_class: type[Exception],
) -> str | None:
    """Validate and return an optional named string value."""

    if raw_value is None:
        return None
    if not isinstance(raw_value, str) or not raw_value.strip():
        raise error_class(f"{file_path} {label} '{key}' must be a non-empty string")
    return raw_value


def optional_named_bool_impl[D: (bool, None)](
    *,
    raw_value: object | None,
    file_path: Path,
    label: str,
    key: str,
    error_class: type[Exception],
    default: D,
) -> bool | D:
    """Validate and return an optional named boolean value."""

    if raw_value is None:
        return default
    if not isinstance(raw_value, bool):
        raise error_class(f"{file_path} {label} '{key}' must be a boolean")
    return raw_value


def optional_bool_impl(
    *,
    entry: dict[str, object],
    key: str,
    file_path: Path,
    label: str,
    error_class: type[Exception],
) -> bool | None:
    """Extract an optional boolean from a mapping."""

    return optional_named_bool_impl(
        raw_value=entry.get(key),
        file_path=file_path,
        label=label,
        key=key,
        error_class=error_class,
        default=None,
    )


def optional_mapping_impl(
    *,
    entry: dict[str, object],
    key: str,
    file_path: Path,
    label: str,
    error_class: type[Exception],
) -> dict[str, object]:
    """Extract an optional mapping from a mapping, defaulting to empty."""

    raw_value: object | None = entry.get(key)
    if raw_value is None:
        return {}
    if not isinstance(raw_value, dict):
        raise error_class(f"{file_path} {label} '{key}' must be a mapping")
    return cast(dict[str, object], raw_value)


def optional_string_tuple_impl(
    *,
    entry: dict[str, object],
    key: str,
    file_path: Path,
    label: str,
    error_class: type[Exception],
) -> tuple[str, ...]:
    """Extract an optional list of strings from a mapping."""

    raw_value: object | None = entry.get(key)
    if raw_value is None:
        return ()
    if not isinstance(raw_value, list):
        raise error_class(f"{file_path} {label} '{key}' must be a list")
    items: list[str] = []
    item: object
    for item in raw_value:
        if not isinstance(item, str):
            raise error_class(f"{file_path} {label} '{key}' entries must be strings")
        items.append(item)
    return tuple(items)
