"""Shared path-default matching and selection entrypoint."""

from __future__ import annotations

from sqlbuild.compiler.discovery.exceptions import DiscoveryConflictError
from sqlbuild.compiler.path_defaults._helpers.matching import (
    is_wildcard,
    matches_prefix,
    specificity,
)
from sqlbuild.compiler.path_defaults.models import PathDefaultSelection


def select_path_default(*, model_path: str, path_keys: tuple[str, ...]) -> PathDefaultSelection:
    """Match and deterministically select a path default for a model path."""

    normalized_path: str = model_path.replace("\\", "/").removeprefix("models/")
    path_parts: tuple[str, ...] = tuple(part for part in normalized_path.split("/") if part)
    matched_keys: tuple[str, ...] = tuple(
        sorted(
            path_key
            for path_key in path_keys
            if matches_prefix(path_parts=path_parts, path_key=path_key)
        )
    )
    literal_matches: tuple[str, ...] = tuple(
        path_key for path_key in matched_keys if not is_wildcard(path_key=path_key)
    )
    if literal_matches:
        return PathDefaultSelection(
            matched_keys=matched_keys,
            selected_key=max(literal_matches, key=lambda path_key: len(path_key.split("/"))),
        )
    if not matched_keys:
        return PathDefaultSelection(matched_keys=(), selected_key=None)

    best_score: tuple[int, int, int] = max(
        specificity(path_key=path_key) for path_key in matched_keys
    )
    best_matches: tuple[str, ...] = tuple(
        path_key for path_key in matched_keys if specificity(path_key=path_key) == best_score
    )
    if len(best_matches) > 1:
        conflicting_keys: str = ", ".join(f"'{path_key}'" for path_key in best_matches)
        raise DiscoveryConflictError(
            f"Model path '{normalized_path}' matches equally specific path_defaults keys: "
            f"{conflicting_keys}.",
            help=(
                "Make one pattern narrower by adding literal or '*' path segments, or remove the "
                "overlap. Path-default selection never depends on declaration order."
            ),
        )
    return PathDefaultSelection(matched_keys=matched_keys, selected_key=best_matches[0])
