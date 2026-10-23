"""Attempt janitor actions and submit them to a worker pool."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from contextvars import copy_context
from time import perf_counter
from typing import Any, cast

from sqlbuild.executor.janitor.models import JanitorActionOutcome


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


def submit_janitor_actions[ItemT, ResultT](
    *,
    pool: ThreadPoolExecutor,
    items: Sequence[ItemT],
    attempt: Callable[[ItemT], JanitorActionOutcome[ResultT]],
) -> dict[Future[JanitorActionOutcome[ResultT]], int]:
    """Each item's submitted attempt, keyed to the item's position."""

    futures: dict[Future[JanitorActionOutcome[ResultT]], int] = {}
    index: int
    item: ItemT
    for index, item in enumerate(items):
        submitted: Future[Any] = pool.submit(copy_context().run, attempt, item)
        futures[cast(Future[JanitorActionOutcome[ResultT]], submitted)] = index
    return futures
