"""Canonical resource identity spelling helpers."""

from __future__ import annotations

from sqlbuild.compiler.resource_names.constants import (
    ACRONYM_BOUNDARY_PATTERN,
    INVALID_CHARACTER_PATTERN,
    UPPERCASE_BOUNDARY_PATTERN,
)


def suggest_resource_identity(*, name: str, private_identity: bool) -> str:
    """Return the suggested canonical spelling for an invalid identity."""

    with_acronym_boundaries: str = ACRONYM_BOUNDARY_PATTERN.sub("_", name.strip())
    with_word_boundaries: str = UPPERCASE_BOUNDARY_PATTERN.sub("_", with_acronym_boundaries)
    replaced: str = INVALID_CHARACTER_PATTERN.sub("_", with_word_boundaries).lower()
    corrected: str = replaced.strip("_") or "resource_name"
    return f"_{corrected}" if private_identity else corrected
