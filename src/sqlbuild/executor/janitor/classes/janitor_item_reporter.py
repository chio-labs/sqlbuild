"""Report each finished janitor action of one chunk to the progress output."""

from __future__ import annotations

from dataclasses import replace

from sqlbuild.executor.janitor.models import (
    JanitorActionDone,
    JanitorActionOutcome,
    JanitorProgressItem,
)
from sqlbuild.executor.janitor.types import JanitorAction, JanitorPhase, JanitorProgress


class JanitorItemReporter:
    """Report one chunk's finished actions by their position in the chunk."""

    def __init__(
        self,
        *,
        progress: JanitorProgress | None,
        phase: JanitorPhase,
        labels: tuple[JanitorProgressItem, ...],
    ) -> None:
        self._progress: JanitorProgress | None = progress
        self._phase: JanitorPhase = phase
        self._labels: tuple[JanitorProgressItem, ...] = labels

    def __call__(
        self, *, index: int, outcome: JanitorActionOutcome[JanitorActionDone | None]
    ) -> None:
        if self._progress is None:
            return
        done: JanitorActionDone | None = outcome.result
        taken: JanitorAction | None = None if done is None else done.taken
        label: JanitorProgressItem = self._labels[index]
        error: str | None = (
            None if outcome.error is None else str(outcome.error) or type(outcome.error).__name__
        )
        self._progress.item_finished(
            phase=self._phase.value,
            item=replace(
                label,
                action=label.action if taken is None else taken,
                error=error,
                duration_seconds=outcome.duration_seconds,
            ),
        )
