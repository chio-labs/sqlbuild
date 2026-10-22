"""Run one janitor apply phase, reporting each action as it finishes."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import replace
from typing import Any

from sqlbuild.executor.janitor.classes.janitor_workers import JanitorWorkers
from sqlbuild.executor.janitor.models import JanitorActionOutcome, JanitorProgressItem
from sqlbuild.executor.janitor.types import JanitorAction, JanitorPhase, JanitorProgress


def run_janitor_phase[T](
    *,
    progress: JanitorProgress | None,
    phase: JanitorPhase,
    items: Sequence[T],
    describe: Callable[[T], JanitorProgressItem],
    apply: Callable[[T, Any], JanitorAction | None],
    workers: JanitorWorkers,
    chunks: Sequence[Sequence[int]] | None = None,
    after_chunk: Callable[[], None] | None = None,
) -> tuple[T, ...]:
    """Apply `apply(item, connection)` to every item and return the items that succeeded.

    Items run concurrently on `workers`, a chunk of item positions at a time (all items when
    `chunks` is none); `after_chunk` runs after every chunk
    and once more after a failure or interruption, before the error is raised. A failing item is
    reported and no later action starts. `apply` may return the action actually taken when it
    differs from the described one.
    """

    if not items:
        return ()
    if progress is not None:
        progress.phase_started(phase=phase.value, total=len(items))
    succeeded: set[int] = set()

    def report(
        chunk: Sequence[int],
    ) -> Callable[[int, JanitorActionOutcome[JanitorAction | None]], None]:
        def on_done(index: int, outcome: JanitorActionOutcome[JanitorAction | None]) -> None:
            item: T = items[chunk[index]]
            if outcome.error is None:
                succeeded.add(chunk[index])
            if progress is None:
                return
            label: JanitorProgressItem = describe(item)
            progress.item_finished(
                phase=phase.value,
                item=label if outcome.result is None else replace(label, action=outcome.result),
                error=None if outcome.error is None else _message(outcome.error),
                duration_seconds=outcome.duration_seconds,
            )

        return on_done

    failure: BaseException | None = None
    try:
        chunk: Sequence[int]
        for chunk in (range(len(items)),) if chunks is None else chunks:
            failure = workers.run(
                items=tuple(items[index] for index in chunk),
                action=apply,
                on_done=report(chunk),
            )
            if failure is not None:
                break
            if after_chunk is not None:
                after_chunk()
    except BaseException:
        _finish_failed(progress=progress, phase=phase, after_chunk=after_chunk)
        raise
    if failure is not None:
        _finish_failed(progress=progress, phase=phase, after_chunk=after_chunk)
        raise failure
    if progress is not None:
        progress.phase_finished(phase=phase.value, failed=False)
    return tuple(item for index, item in enumerate(items) if index in succeeded)


def _finish_failed(
    *,
    progress: JanitorProgress | None,
    phase: JanitorPhase,
    after_chunk: Callable[[], None] | None,
) -> None:
    try:
        if after_chunk is not None:
            after_chunk()
    finally:
        if progress is not None:
            progress.phase_finished(phase=phase.value, failed=True)


def _message(error: BaseException) -> str:
    return str(error) or type(error).__name__
