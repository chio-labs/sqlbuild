"""Rejection of unsupported keys in SQLBuild statement headers."""

from __future__ import annotations

from collections.abc import Iterable

import sqlbuild._native as _native
from sqlbuild.compiler.discovery.exceptions import DiscoveryError


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
        help=_native.unsupported_keys_help(list(unsupported), list(supported_keys)),
    )
