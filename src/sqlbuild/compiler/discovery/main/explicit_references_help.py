"""Entry for the migration help that relaxes explicit references."""

from __future__ import annotations

from sqlbuild.compiler.discovery._helpers.settings.guidance import (
    explicit_references_help as _explicit_references_help,
)


def explicit_references_help(*, allowed: str) -> str:
    """Show the current `[references] enforce_explicit` value and the exact TOML to relax it."""

    return _explicit_references_help(allowed=allowed)
