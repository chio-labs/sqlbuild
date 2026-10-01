"""Rejection of unsupported keys in SQLBuild statement headers."""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

from sqlbuild.compiler.discovery._helpers.validation.supported_keys import unsupported_keys_help
from sqlbuild.compiler.discovery.exceptions import DiscoveryError


def reject_unsupported_header_keys(
    *,
    header_values: dict[str, object],
    supported_keys: frozenset[str],
    statement: str,
    header: str,
    header_line: int,
    file_path: Path,
    error_class: type[DiscoveryError],
) -> None:
    """Raise when a header declares keys outside its set; `header_line` is 1-based."""

    unsupported: tuple[str, ...] = tuple(
        str(key) for key in header_values if key not in supported_keys
    )
    if not unsupported:
        return
    line: int = header_line + header.count(
        "\n", 0, _header_key_offset(header=header, key=unsupported[0])
    )
    raise unsupported_keys_error(
        statement=statement,
        location=f"{file_path}:{line}",
        keys=unsupported,
        supported_keys=supported_keys,
        error_class=error_class,
    )


def unsupported_keys_error(
    *,
    statement: str,
    location: str,
    keys: Iterable[str],
    supported_keys: frozenset[str],
    error_class: type[DiscoveryError],
) -> DiscoveryError:
    """Build the shared unsupported-keys error with a nearest-key suggestion."""

    unsupported: tuple[str, ...] = tuple(keys)
    return error_class(
        f"{statement} in '{location}' has unsupported keys: {', '.join(unsupported)}",
        help=unsupported_keys_help(keys=unsupported, supported_keys=supported_keys),
    )


def _header_key_offset(*, header: str, key: str) -> int:
    match: re.Match[str] | None = re.search(
        rf"(?:^|[(,])(?:\s|--[^\n]*(?:\n|$)|/\*.*?\*/)*({re.escape(key)})\b", header, re.S
    )
    return match.start(1) if match is not None else 0
