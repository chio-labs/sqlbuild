"""Clone prephase progress callback."""

from __future__ import annotations

from collections.abc import Callable

from sqlbuild.executor.clone.classes.progress_state import CloneProgressState
from sqlbuild.executor.clone.models import CloneItemResult


class ClonePrephaseProgressReporter:
    """Report completed clone items against owned shared progress state."""

    def __init__(
        self,
        *,
        progress: CloneProgressState,
        report_item: Callable[..., None],
    ) -> None:
        self._progress: CloneProgressState = progress
        self._report_item: Callable[..., None] = report_item

    def __call__(self, *, index: int, total: int, item: CloneItemResult) -> None:
        self._progress.update(completed=index, total=total)
        self._report_item(index=index, total=total, item=item)
