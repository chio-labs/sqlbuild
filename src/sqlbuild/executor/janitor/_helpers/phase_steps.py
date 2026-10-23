"""Steps of one janitor apply phase: announcements, chunk positions and finished actions."""

from __future__ import annotations

from collections.abc import Sequence

from sqlbuild.executor.janitor.models import (
    JanitorActionDone,
    JanitorActionOutcome,
    JanitorChunkOutcome,
)
from sqlbuild.executor.janitor.types import JanitorPhase, JanitorProgress
from sqlbuild.executor.janitor_events.models import JanitorEventRecord


def announce_phase(*, progress: JanitorProgress | None, phase: JanitorPhase, total: int) -> None:
    """Report that a phase starts `total` actions."""

    if progress is not None:
        progress.phase_started(phase=phase.value, total=total)


def close_phase(*, progress: JanitorProgress | None, phase: JanitorPhase, failed: bool) -> None:
    """Report that a phase finished or failed."""

    if progress is not None:
        progress.phase_finished(phase=phase.value, failed=failed)


def chunk_positions(
    *, total: int, chunks: Sequence[Sequence[int]] | None
) -> tuple[tuple[int, ...], ...]:
    """The item positions of each chunk, or every position as one chunk."""

    if chunks is None:
        return (tuple(range(total)),)
    return tuple(tuple(chunk) for chunk in chunks)


def finished_actions(
    *,
    positions: tuple[int, ...],
    chunk: JanitorChunkOutcome[JanitorActionDone | None],
) -> tuple[tuple[int, JanitorActionDone], ...]:
    """Each succeeded item's phase position and what it did."""

    pairs: list[tuple[int, JanitorActionDone]] = []
    position: int
    outcome: JanitorActionOutcome[JanitorActionDone | None] | None
    for position, outcome in zip(positions, chunk.outcomes, strict=True):
        if outcome is not None and outcome.error is None:
            pairs.append((position, outcome.result or JanitorActionDone()))
    return tuple(pairs)


def chunk_failure(chunk: JanitorChunkOutcome[JanitorActionDone | None]) -> BaseException | None:
    """The chunk's interrupt, else its earliest item failure, else its report error."""

    if chunk.interruption is not None:
        return chunk.interruption
    return next(
        (outcome.error for outcome in chunk.outcomes if outcome is not None and outcome.error),
        chunk.report_error,
    )


def report_unwritten_events(
    *,
    progress: JanitorProgress | None,
    finished: tuple[JanitorActionDone, ...],
    error: BaseException,
) -> None:
    """Warn which completed actions' audit events a failed write left out, by schema."""

    events: tuple[JanitorEventRecord, ...] = tuple(
        done.event for done in finished if done.event is not None
    )
    if progress is None or not events:
        return
    schemas: tuple[str, ...] = tuple(sorted({_schema_name(event) for event in events}))
    progress.events_unwritten(
        count=len(events), schemas=schemas, error=str(error) or type(error).__name__
    )


def raise_phase_failure(
    *,
    progress: JanitorProgress | None,
    phase: JanitorPhase,
    failure: BaseException | None,
    flush_error: BaseException | None,
) -> None:
    """Close the phase as failed and raise its failure; an interrupt wins, the other is chained."""

    primary: BaseException | None
    secondary: BaseException | None
    primary, secondary = _ranked(failure=failure, flush_error=flush_error)
    if primary is None:
        return
    if secondary is not None:
        primary.__context__ = secondary
    if flush_error is not None and primary is not flush_error:
        primary.add_note(f"Audit events of completed actions were not written: {flush_error}")
    try:
        close_phase(progress=progress, phase=phase, failed=True)
    finally:
        raise primary


def _ranked(
    *, failure: BaseException | None, flush_error: BaseException | None
) -> tuple[BaseException | None, BaseException | None]:
    """The error to raise and the one to chain: an interrupt first, else the original failure."""

    flush_interrupted: bool = flush_error is not None and not isinstance(flush_error, Exception)
    if failure is None or (flush_interrupted and isinstance(failure, Exception)):
        return flush_error, failure
    return failure, flush_error


def _schema_name(event: JanitorEventRecord) -> str:
    if event.relation_database is None:
        return event.relation_schema
    return f"{event.relation_database}.{event.relation_schema}"
