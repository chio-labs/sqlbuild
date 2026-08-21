"""Resolve an offset in expanded SQL back onto the authored body."""

from __future__ import annotations

from sqlbuild.compiler.compile._helpers.render.spans import map_through_passes
from sqlbuild.compiler.compile.models import ExpansionSpan, MappedOffset


def map_expanded_offset(
    *, offset: int, passes: tuple[tuple[ExpansionSpan, ...], ...]
) -> MappedOffset:
    """Resolve an offset in expanded SQL back onto the authored body."""

    return map_through_passes(offset=offset, passes=passes)
