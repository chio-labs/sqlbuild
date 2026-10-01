"""Run independent warehouse inspection reads with bounded concurrency."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from contextvars import copy_context
from typing import cast

from sqlbuild.adapter.relations.types import InspectionCompletion


def run_bounded_inspections[ResultT](
    *,
    tasks: Sequence[Callable[[], ResultT]],
    concurrency: int,
    on_complete: InspectionCompletion[ResultT] | None = None,
) -> list[ResultT]:
    """Return results in input order, report completions on this thread, raise lowest failure."""

    if concurrency <= 1 or len(tasks) <= 1:
        results: list[ResultT] = []
        index: int
        task: Callable[[], ResultT]
        for index, task in enumerate(tasks):
            result: ResultT = task()
            if on_complete is not None:
                on_complete(index=index, result=result)
            results.append(result)
        return results
    completed: dict[int, ResultT] = {}
    failures: dict[int, BaseException] = {}
    with ThreadPoolExecutor(max_workers=min(concurrency, len(tasks))) as pool:
        futures: dict[Future[ResultT], int] = {
            cast(Future[ResultT], pool.submit(copy_context().run, task)): index
            for index, task in enumerate(tasks)
        }
        future: Future[ResultT]
        for future in as_completed(futures):
            if future.cancelled():
                continue
            future_index: int = futures[future]
            error: BaseException | None = future.exception()
            if error is not None:
                failures[future_index] = error
                pending: Future[ResultT]
                for pending in futures:
                    _ = pending.cancel()
                continue
            completed[future_index] = future.result()
            if on_complete is not None and not failures:
                on_complete(index=future_index, result=completed[future_index])
    if failures:
        raise failures[min(failures)]
    return [completed[index] for index in range(len(tasks))]
