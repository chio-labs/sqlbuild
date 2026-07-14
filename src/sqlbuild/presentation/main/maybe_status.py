"""Public transient stderr status context entry."""

from __future__ import annotations

import sys
from collections.abc import Iterator
from contextlib import contextmanager

from sqlbuild.presentation._helpers.progress import progress_spinners_disabled
from sqlbuild.presentation.classes.transient_status_reporter import TransientStatusReporter


@contextmanager
def maybe_status(*, message: str, enabled: bool) -> Iterator[None]:
    """Render a stderr spinner for long-running interactive operations."""

    if not enabled or progress_spinners_disabled() or not sys.stderr.isatty():
        yield
        return
    reporter: TransientStatusReporter = TransientStatusReporter(stream=sys.stderr, enabled=enabled)
    reporter.start(message)
    try:
        yield
    finally:
        reporter.close()
