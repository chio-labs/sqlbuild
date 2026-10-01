"""Run independent warehouse inspection reads with bounded concurrency."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from contextvars import copy_context
from typing import cast

from sqlbuild.adapter.relations._helpers.inspection_context import (
    inside_inspection_worker,
    mark_inspection_worker,
)
from sqlbuild.adapter.relations.types import InspectionCompletion


def run_bounded_inspections[ResultT](
    *,
    tasks: Sequence[Callable[[], ResultT]],
    concurrency: int,
    on_complete: InspectionCompletion[ResultT] | None = None,
) -> list[ResultT]:
    """Return ordered results, raising the lowest failure; nested calls run serially."""

    if concurrency <= 1 or len(tasks) <= 1 or inside_inspection_worker():
        results: list[ResultT] = []
        index: int
        task: Callable[[], ResultT]
        for index, task in enumerate(tasks):
            result: ResultT = task()
            if on_complete is not None:
                on_complete(index=index, result=result)
            results.append(result)
        return results
    pool: ThreadPoolExecutor = ThreadPoolExecutor(max_workers=min(concurrency, len(tasks)))
    try:
        completed: dict[int, ResultT] = _collect(pool=pool, tasks=tasks, on_complete=on_complete)
    except BaseException:
        pool.shutdown(wait=False, cancel_futures=True)
        raise
    pool.shutdown(wait=True)
    return [completed[index] for index in range(len(tasks))]


def _collect[ResultT](
    *,
    pool: ThreadPoolExecutor,
    tasks: Sequence[Callable[[], ResultT]],
    on_complete: InspectionCompletion[ResultT] | None,
) -> dict[int, ResultT]:
    """Stop starting tasks after a failure, let running ones finish, raise the lowest failure."""

    futures: dict[Future[ResultT], int] = {
        cast(Future[ResultT], pool.submit(copy_context().run, _run_as_worker, task)): index
        for index, task in enumerate(tasks)
    }
    completed: dict[int, ResultT] = {}
    failures: dict[int, BaseException] = {}
    future: Future[ResultT]
    for future in as_completed(futures):
        if future.cancelled():
            continue
        future_index: int = futures[future]
        error: BaseException | None = future.exception()
        if error is not None:
            if not failures:
                pending: Future[ResultT]
                for pending in futures:
                    _ = pending.cancel()
            failures[future_index] = error
            continue
        completed[future_index] = future.result()
        if on_complete is not None and not failures:
            on_complete(index=future_index, result=completed[future_index])
    if failures:
        raise failures[min(failures)]
    return completed


def _run_as_worker[ResultT](task: Callable[[], ResultT]) -> ResultT:
    _ = mark_inspection_worker()
    return task()
