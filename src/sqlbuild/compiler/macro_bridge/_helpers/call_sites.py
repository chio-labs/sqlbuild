"""Native macro call-site scans and splices of one authored string."""

from __future__ import annotations

import sys
import unicodedata

import sqlbuild._native as _native
from sqlbuild.compiler.compile.models import ExpansionSpan
from sqlbuild.compiler.macro_bridge.models import MacroCallScan, MacroCallSite, MacroScanFailure


def scan_macro_calls(
    sql: str,
    *,
    python_version: tuple[int, int] | None = None,
    unicode_version: str | None = None,
) -> MacroCallScan:
    """The complete top-level call sites of `sql`, and where its scan raises, if it does."""

    rows: list[tuple[int, int, str, list[str] | None, bool]]
    failure: tuple[int | None, str] | None
    rows, failure = _native.scan_macro_call_sites(
        sql,
        python_version or (sys.version_info[0], sys.version_info[1]),
        unicode_version or unicodedata.unidata_version,
    )
    return MacroCallScan(
        sites=tuple(
            MacroCallSite(
                start=start,
                end=end,
                name=name,
                tree_names=None if tree_names is None else tuple(tree_names),
                typed_reference_text=typed_reference_text,
            )
            for start, end, name, tree_names, typed_reference_text in rows
        ),
        failure=None
        if failure is None
        else MacroScanFailure(call_start=failure[0], message=failure[1]),
    )


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
