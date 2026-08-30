"""Non-degrading debug process resource reporting."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlbuild.diagnostics.classes.process_resource_tracker import ProcessResourceTracker
from sqlbuild.diagnostics.main._log_process_resources import log_process_resources
from sqlbuild.diagnostics.models import ProcessResourceUsage


def _start_process_resource_tracking(*, enabled: bool) -> ProcessResourceTracker | None:
    try:
        return ProcessResourceTracker() if enabled else None
    except BaseException:
        return None


def _finish_process_resource_tracking(*, tracker: ProcessResourceTracker | None) -> None:
    if tracker is None:
        return
    try:
        usage: ProcessResourceUsage = tracker.finish()
    except BaseException:
        return
    try:
        log_process_resources(usage=usage)
    except BaseException:
        return


@contextmanager
def process_resource_reporting(*, enabled: bool) -> Iterator[None]:
    """Report debug process resources without changing the wrapped outcome."""

    tracker: ProcessResourceTracker | None = _start_process_resource_tracking(enabled=enabled)
    try:
        yield
    finally:
        _ = _finish_process_resource_tracking(tracker=tracker)
