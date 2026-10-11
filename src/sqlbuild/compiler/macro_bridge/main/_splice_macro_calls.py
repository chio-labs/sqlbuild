"""Splice macro call outputs into one authored string natively."""

from __future__ import annotations

import sqlbuild._native as _native
from sqlbuild.compiler.compile.models import ExpansionSpan
from sqlbuild.compiler.macro_bridge.models import MacroCallSite


def splice_macro_calls(
    *, sql: str, sites: tuple[MacroCallSite, ...], outputs: list[str]
) -> tuple[str, tuple[ExpansionSpan, ...]]:
    """Replace each call site with its output, returning the SQL and substitution spans."""

    rendered: str
    spans: list[tuple[int, int, int, int]]
    rendered, spans = _native.splice_macro_calls(
        sql, [(site.start, site.end) for site in sites], outputs
    )
    return rendered, tuple(
        ExpansionSpan(
            source_start=source_start,
            source_end=source_end,
            output_start=output_start,
            output_end=output_end,
        )
        for source_start, source_end, output_start, output_end in spans
    )
