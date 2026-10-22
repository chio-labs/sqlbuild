"""Run one janitor apply phase, reporting each action as it finishes."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import replace
from time import perf_counter

from sqlbuild.executor.janitor.models import JanitorProgressItem
from sqlbuild.executor.janitor.types import JanitorAction, JanitorPhase, JanitorProgress


def run_janitor_phase[T](
    *,
    progress: JanitorProgress | None,
    phase: JanitorPhase,
    items: Sequence[T],
    describe: Callable[[T], JanitorProgressItem],
    apply: Callable[[T], JanitorAction | None],
) -> None:
    """Apply `apply` to each item in order; a failing item is reported, then re-raised.

    `apply` may return the action actually taken when it differs from the described one.
    """

    if not items:
        return
    if progress is not None:
        progress.phase_started(phase=phase.value, total=len(items))
    item: T
    for item in items:
        started: float = perf_counter()
        try:
            taken: JanitorAction | None = apply(item)
        except BaseException as error:
            message: str = str(error) or type(error).__name__
            _report(progress, phase, (describe(item), None), (message, started))
            if progress is not None:
                progress.phase_finished(phase=phase.value, failed=True)
            raise
        _report(progress, phase, (describe(item), taken), (None, started))
    if progress is not None:
        progress.phase_finished(phase=phase.value, failed=False)


def _report(
    progress: JanitorProgress | None,
    phase: JanitorPhase,
    described: tuple[JanitorProgressItem, JanitorAction | None],
    outcome: tuple[str | None, float],
) -> None:
    if progress is None:
        return
    label: JanitorProgressItem
    taken: JanitorAction | None
    label, taken = described
    error: str | None
    started: float
    error, started = outcome
    progress.item_finished(
        phase=phase.value,
        item=label if taken is None else replace(label, action=taken),
        error=error,
        duration_seconds=perf_counter() - started,
    )
