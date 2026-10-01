"""Shared rejection of unsupported keys in authored configuration mappings."""

from __future__ import annotations

from collections.abc import Mapping
from difflib import get_close_matches
from pathlib import Path

from sqlbuild.compiler.discovery.exceptions import DiscoveryError

_SUGGESTION_CUTOFF: float = 0.6
_LISTED_SUPPORTED_KEYS_LIMIT: int = 12


def unsupported_keys_help(*, keys: tuple[str, ...], supported_keys: frozenset[str]) -> str:
    """Suggest the nearest supported key for each unsupported key."""

    candidates: list[str] = sorted(supported_keys)
    suggestions: list[str] = []
    for key in keys:
        matches: list[str] = get_close_matches(key, candidates, n=1, cutoff=_SUGGESTION_CUTOFF)
        if matches:
            suggestions.append(
                f"'{matches[0]}'" if len(keys) == 1 else f"'{matches[0]}' for '{key}'"
            )
    if suggestions:
        return f"did you mean {', '.join(suggestions)}?"
    if len(candidates) <= _LISTED_SUPPORTED_KEYS_LIMIT:
        return f"supported keys: {', '.join(candidates)}"
    return "remove the key; see the reference for supported keys"


def reject_unknown_mapping_keys(
    *,
    mapping: Mapping[str, object],
    allowed: frozenset[str],
    file_path: Path,
    label: str,
    error_class: type[DiscoveryError],
) -> None:
    """Raise when a YAML mapping declares keys outside its allowed set."""

    unknown: tuple[str, ...] = tuple(sorted(str(key) for key in mapping if key not in allowed))
    if unknown:
        raise error_class(
            f"{file_path} {label} has unknown keys: {', '.join(unknown)}; allowed keys: "
            f"{', '.join(sorted(allowed))}",
            help=unsupported_keys_help(keys=unknown, supported_keys=allowed),
        )
