"""Run one janitor apply phase, reporting each action as it finishes."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from sqlbuild.executor.janitor._helpers.phase_steps import (
    announce_phase,
    chunk_failure,
    chunk_positions,
    close_phase,
    finished_actions,
)
from sqlbuild.executor.janitor.classes.janitor_item_reporter import JanitorItemReporter
from sqlbuild.executor.janitor.classes.janitor_workers import JanitorWorkers
from sqlbuild.executor.janitor.models import (
    JanitorActionDone,
    JanitorChunkOutcome,
    JanitorProgressItem,
)
from sqlbuild.executor.janitor.types import JanitorPhase, JanitorProgress


def run_janitor_phase[T](
    *,
    progress: JanitorProgress | None,
    phase: JanitorPhase,
    items: Sequence[T],
    describe: Callable[[T], JanitorProgressItem],
    apply: Callable[..., JanitorActionDone | None],
    workers: JanitorWorkers,
    chunks: Sequence[Sequence[int]] | None = None,
    after_chunk: Callable[[tuple[JanitorActionDone, ...]], None] | None = None,
) -> tuple[tuple[T, JanitorActionDone], ...]:
    """Apply `apply(item=, connection=)` chunk by chunk; return succeeded items in plan order."""

    if not items:
        return ()
    _ = announce_phase(progress=progress, phase=phase, total=len(items))
    finished: list[tuple[int, JanitorActionDone]] = []
    positions: tuple[int, ...]
    for positions in chunk_positions(total=len(items), chunks=chunks):
        chunk: JanitorChunkOutcome[JanitorActionDone | None] = workers.run(
            items=tuple(items[position] for position in positions),
            action=apply,
            on_done=JanitorItemReporter(
                progress=progress,
                phase=phase,
                labels=tuple(describe(items[position]) for position in positions),
            ),
        )
        succeeded: tuple[tuple[int, JanitorActionDone], ...] = finished_actions(
            positions=positions, chunk=chunk
        )
        finished.extend(succeeded)
        failure: BaseException | None = chunk_failure(chunk)
        try:
            if after_chunk is not None:
                _ = after_chunk(tuple(done for _, done in succeeded))
        except BaseException:
            _ = close_phase(progress=progress, phase=phase, failed=True)
            raise
        if failure is not None:
            _ = close_phase(progress=progress, phase=phase, failed=True)
            raise failure
    _ = close_phase(progress=progress, phase=phase, failed=False)
    return tuple((items[position], done) for position, done in sorted(finished, key=_position))


def _position(pair: tuple[int, JanitorActionDone]) -> int:
    return pair[0]
