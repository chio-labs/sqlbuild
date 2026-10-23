"""Run one janitor apply phase, reporting each action as it finishes."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from sqlbuild.executor.janitor._helpers.phase_steps import (
    announce_phase,
    chunk_failure,
    chunk_positions,
    close_phase,
    finished_actions,
    raise_phase_failure,
    report_unwritten_events,
)
from sqlbuild.executor.janitor.classes.janitor_chunk_collector import JanitorChunkCollector
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
        collector: JanitorChunkCollector[JanitorActionDone | None] = JanitorChunkCollector(
            size=len(positions),
            on_done=JanitorItemReporter(
                progress=progress,
                phase=phase,
                labels=tuple(describe(items[position]) for position in positions),
            ),
        )
        try:
            _ = workers.run(
                items=tuple(items[position] for position in positions),
                action=apply,
                collector=collector,
            )
        except BaseException as error:
            _ = collector.interrupt(error)
        chunk: JanitorChunkOutcome[JanitorActionDone | None] = collector.outcome()
        succeeded: tuple[tuple[int, JanitorActionDone], ...] = finished_actions(
            positions=positions, chunk=chunk
        )
        finished.extend(succeeded)
        completed: tuple[JanitorActionDone, ...] = tuple(done for _, done in succeeded)
        flush_error: BaseException | None = None
        try:
            if after_chunk is not None:
                _ = after_chunk(completed)
        except BaseException as error:
            flush_error = error
            _ = report_unwritten_events(progress=progress, finished=completed, error=error)
        _ = raise_phase_failure(
            progress=progress,
            phase=phase,
            failure=chunk_failure(chunk),
            flush_error=flush_error,
        )
    _ = close_phase(progress=progress, phase=phase, failed=False)
    return tuple((items[position], done) for position, done in sorted(finished, key=_position))


def _position(pair: tuple[int, JanitorActionDone]) -> int:
    return pair[0]
