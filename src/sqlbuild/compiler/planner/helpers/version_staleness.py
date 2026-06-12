"""Pure expected-vs-built model version staleness helpers."""

from __future__ import annotations

from collections.abc import Mapping


def build_stale_model_names_from_version_identities(
    *,
    model_names: tuple[str, ...],
    expected_version_hashes: Mapping[str, str],
    built_version_hashes: Mapping[str, str | None],
    forced_stale_model_names: tuple[str, ...] = (),
) -> tuple[str, ...]:
    """Return models with missing/mismatched built hashes or external stale markers."""

    forced_stale: set[str] = set(forced_stale_model_names)
    return tuple(
        model_name
        for model_name in model_names
        if model_name in forced_stale
        or built_version_hashes.get(model_name) != expected_version_hashes.get(model_name)
    )
