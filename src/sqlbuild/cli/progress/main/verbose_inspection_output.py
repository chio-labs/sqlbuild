"""Verbose per-query warehouse inspection output on stderr."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlbuild.adapter.relations.main.inspection_query_sink import inspection_query_sink
from sqlbuild.cli.progress.classes.verbose_inspection_writer import VerboseInspectionWriter


@contextmanager
def verbose_inspection_output(*, enabled: bool) -> Iterator[None]:
    """Write each inspection read, then a total, to stderr while ``enabled``."""

    if not enabled:
        yield
        return
    writer: VerboseInspectionWriter = VerboseInspectionWriter()
    with inspection_query_sink(writer.write):
        yield
    writer.write_total()
