"""Steps of one janitor apply phase: announcements, chunk positions and finished actions."""

from __future__ import annotations

from collections.abc import Sequence

from sqlbuild.executor.janitor.models import (
    JanitorActionDone,
    JanitorActionOutcome,
    JanitorChunkOutcome,
)
from sqlbuild.executor.janitor.types import JanitorPhase, JanitorProgress


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
    """The interrupt that stopped the chunk, else the earliest item's failure."""

    if chunk.interruption is not None:
        return chunk.interruption
    return next(
        (outcome.error for outcome in chunk.outcomes if outcome is not None and outcome.error),
        None,
    )
