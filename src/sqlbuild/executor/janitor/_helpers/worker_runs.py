"""Attempt janitor actions and submit them to a worker pool."""

from __future__ import annotations

from collections.abc import Callable
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


def submit_janitor_action[ItemT, ResultT](
    *,
    pool: ThreadPoolExecutor,
    item: ItemT,
    attempt: Callable[[ItemT], JanitorActionOutcome[ResultT]],
) -> Future[JanitorActionOutcome[ResultT]]:
    """The submitted attempt of one item, run in a copy of the caller's context."""

    submitted: Future[Any] = pool.submit(copy_context().run, attempt, item)
    return cast(Future[JanitorActionOutcome[ResultT]], submitted)
