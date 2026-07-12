"""Interactive compile status helpers."""

from __future__ import annotations

import sys
import time

from sqlbuild.presentation.classes.transient_status_reporter import TransientStatusReporter


def elapsed_ms(start: float) -> int:
    return int((time.monotonic() - start) * 1000)


def start_compile_status(*, json_output: bool, no_color: bool) -> TransientStatusReporter | None:
    """Create an interactive-only compile status reporter."""

    if json_output:
        return None
    if not hasattr(sys.stdout, "isatty") or not sys.stdout.isatty():
        return None
    return TransientStatusReporter(
        stream=sys.stdout,
        use_color=not no_color,
    )


def start_compile_phase(*, status: TransientStatusReporter | None, message: str) -> None:
    if status is not None:
        status.start(message)


def complete_compile_phase(*, status: TransientStatusReporter | None, message: str) -> None:
    if status is not None:
        status.complete(message=message)
