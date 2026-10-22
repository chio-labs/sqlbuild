"""Attempt janitor actions and collect concurrent outcomes in completion order."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from contextvars import copy_context
from time import perf_counter
from typing import Any, cast

from sqlbuild.executor.janitor.models import JanitorActionOutcome, JanitorChunkOutcome

type _Pending[ResultT] = set[Future[JanitorActionOutcome[ResultT]]]


def attempt_janitor_action[ResultT](
    *, action: Callable[..., ResultT], item: object, connection: Any
) -> JanitorActionOutcome[ResultT]:
    """Run `action(item=, connection=)`, capturing its result or error and its duration."""

    started: float = perf_counter()
    try:
        result: ResultT = action(item=item, connection=connection)
    except BaseException as error:
        return JanitorActionOutcome(error=error, duration_seconds=perf_counter() - started)
    return JanitorActionOutcome(result=result, duration_seconds=perf_counter() - started)


def collect_janitor_outcomes[ItemT, ResultT](
    *,
    pool: ThreadPoolExecutor,
    items: Sequence[ItemT],
    attempt: Callable[[ItemT], JanitorActionOutcome[ResultT]],
    on_done: Callable[..., None],
) -> JanitorChunkOutcome[ResultT]:
    """Report outcomes as they finish; after a failure or interrupt, start nothing more."""

    futures: dict[Future[JanitorActionOutcome[ResultT]], int] = {}
    index: int
    item: ItemT
    for index, item in enumerate(items):
        submitted: Future[Any] = pool.submit(copy_context().run, attempt, item)
        futures[cast(Future[JanitorActionOutcome[ResultT]], submitted)] = index
    outcomes: dict[int, JanitorActionOutcome[ResultT]] = {}
    pending: _Pending[ResultT] = set(futures)
    try:
        while pending:
            done: _Pending[ResultT]
            done, pending = wait(pending, return_when=FIRST_COMPLETED)
            reported: dict[int, JanitorActionOutcome[ResultT]]
            reported, pending = _report(
                done=done, pending=pending, futures=futures, on_done=on_done
            )
            outcomes.update(reported)
    except BaseException as interruption:
        _cancel(pending=pending)
        finished: dict[int, JanitorActionOutcome[ResultT]] = _report(
            done=wait(pending).done, pending=set(), futures=futures, on_done=on_done
        )[0]
        outcomes.update(finished)
        return JanitorChunkOutcome(
            outcomes=_in_order(outcomes=outcomes, count=len(items)), interruption=interruption
        )
    return JanitorChunkOutcome(outcomes=_in_order(outcomes=outcomes, count=len(items)))


def _report[ResultT](
    *,
    done: _Pending[ResultT],
    pending: _Pending[ResultT],
    futures: dict[Future[JanitorActionOutcome[ResultT]], int],
    on_done: Callable[..., None],
) -> tuple[dict[int, JanitorActionOutcome[ResultT]], _Pending[ResultT]]:
    """Report finished outcomes in item order and cancel the rest once one failed."""

    reported: dict[int, JanitorActionOutcome[ResultT]] = {}
    future: Future[JanitorActionOutcome[ResultT]]
    for future in sorted(done, key=futures.__getitem__):
        if future.cancelled():
            continue
        outcome: JanitorActionOutcome[ResultT] = future.result()
        reported[futures[future]] = outcome
        _ = on_done(index=futures[future], outcome=outcome)
        if outcome.error is not None:
            _cancel(pending=pending)
    return reported, {future for future in pending if not future.cancelled()}


def _cancel[ResultT](*, pending: _Pending[ResultT]) -> None:
    future: Future[JanitorActionOutcome[ResultT]]
    for future in pending:
        _ = future.cancel()


def _in_order[ResultT](
    *, outcomes: dict[int, JanitorActionOutcome[ResultT]], count: int
) -> tuple[JanitorActionOutcome[ResultT] | None, ...]:
    return tuple(outcomes.get(index) for index in range(count))
