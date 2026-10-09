"""Source maps for located reference extraction errors."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import ExpansionSpan, SqlReferenceSourceMap


def source_map_at(
    *, body_start: int, passes: tuple[tuple[ExpansionSpan, ...], ...] = ()
) -> SqlReferenceSourceMap:
    """Return a source map whose authored body starts at `body_start` in its file."""

    return SqlReferenceSourceMap(body_start=lambda: body_start, passes=passes)
