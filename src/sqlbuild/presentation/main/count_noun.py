"""Public counted noun rendering entry."""

from __future__ import annotations

from sqlbuild.presentation._helpers.structure import format_count_noun as _format_count_noun


def format_count_noun(*, count: int, singular: str, plural: str | None = None) -> str:
    """Render a count with the singular noun for one and the plural noun otherwise."""

    return _format_count_noun(count=count, singular=singular, plural=plural)
