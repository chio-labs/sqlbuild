"""Shared rejection of unsupported keys in authored configuration mappings."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import sqlbuild._native as _native
from sqlbuild.compiler.discovery.exceptions import DiscoveryError


def reject_unknown_mapping_keys(
    *,
    mapping: Mapping[str, object],
    allowed: frozenset[str],
    file_path: Path,
    label: str,
    error_class: type[DiscoveryError],
) -> None:
    """Raise when a YAML mapping declares keys outside its allowed set."""

    failure: tuple[str, str] | None = _native.unknown_mapping_keys(
        [(str(key), isinstance(key, str)) for key in mapping], list(allowed)
    )
    if failure is not None:
        raise error_class(f"{file_path} {label} {failure[0]}", help=failure[1])
