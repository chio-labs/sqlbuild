"""Bounded concurrent janitor actions, one warehouse connection per worker."""

from __future__ import annotations

import queue
from collections.abc import Callable, Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from contextvars import copy_context
from time import perf_counter
from typing import Any

from sqlbuild.executor.janitor.models import JanitorActionOutcome


class JanitorWorkers:
    """Run independent janitor actions, each on a connection no other action is using."""

    def __init__(self, *, connections: tuple[Any, ...]) -> None:
        self.connections: tuple[Any, ...] = connections

    @property
    def connection(self) -> Any:
        """The invocation's own connection, used for everything outside a phase's actions."""

        return self.connections[0]

    def run[ItemT, ResultT](
        self,
        *,
        items: Sequence[ItemT],
        action: Callable[[ItemT, Any], ResultT],
        on_done: Callable[[int, JanitorActionOutcome[ResultT]], None],
    ) -> BaseException | None:
        """Run `action` on every item, reporting each on the calling thread as it finishes.

        After a failure no further action starts; running ones finish and are reported. The
        failure of the earliest item is returned.
        """

        if len(self.connections) == 1 or len(items) <= 1:
            return self._run_in_order(items=items, action=action, on_done=on_done)
        connections: queue.Queue[Any] = queue.Queue()
        connection: Any
        for connection in self.connections:
            connections.put(connection)

        def attempt(item: ItemT) -> JanitorActionOutcome[ResultT]:
            borrowed: Any = connections.get()
            try:
                return _attempt(action=action, item=item, connection=borrowed)
            finally:
                connections.put(borrowed)

        pool: ThreadPoolExecutor = ThreadPoolExecutor(
            max_workers=min(len(self.connections), len(items))
        )
        try:
            return _collect(pool=pool, items=items, attempt=attempt, on_done=on_done)
        finally:
            pool.shutdown(wait=True, cancel_futures=True)

    def _run_in_order[ItemT, ResultT](
        self,
        *,
        items: Sequence[ItemT],
        action: Callable[[ItemT, Any], ResultT],
        on_done: Callable[[int, JanitorActionOutcome[ResultT]], None],
    ) -> BaseException | None:
        index: int
        item: ItemT
        for index, item in enumerate(items):
            outcome: JanitorActionOutcome[ResultT] = _attempt(
                action=action, item=item, connection=self.connection
            )
            on_done(index, outcome)
            if outcome.error is not None:
                return outcome.error
        return None


def _attempt[ItemT, ResultT](
    *, action: Callable[[ItemT, Any], ResultT], item: ItemT, connection: Any
) -> JanitorActionOutcome[ResultT]:
    started: float = perf_counter()
    try:
        result: ResultT = action(item, connection)
    except BaseException as error:
        return JanitorActionOutcome(error=error, duration_seconds=perf_counter() - started)
    return JanitorActionOutcome(result=result, duration_seconds=perf_counter() - started)


def _collect[ItemT, ResultT](
    *,
    pool: ThreadPoolExecutor,
    items: Sequence[ItemT],
    attempt: Callable[[ItemT], JanitorActionOutcome[ResultT]],
    on_done: Callable[[int, JanitorActionOutcome[ResultT]], None],
) -> BaseException | None:
    futures: dict[Future[JanitorActionOutcome[ResultT]], int] = {
        pool.submit(copy_context().run, attempt, item): index for index, item in enumerate(items)
    }
    failures: dict[int, BaseException] = {}
    pending: set[Future[JanitorActionOutcome[ResultT]]] = set(futures)
    while pending:
        done: set[Future[JanitorActionOutcome[ResultT]]]
        done, pending = wait(pending, return_when=FIRST_COMPLETED)
        future: Future[JanitorActionOutcome[ResultT]]
        for future in sorted(done, key=futures.__getitem__):
            if future.cancelled():
                continue
            outcome: JanitorActionOutcome[ResultT] = future.result()
            on_done(futures[future], outcome)
            if outcome.error is None:
                continue
            if not failures:
                for waiting in pending:
                    _ = waiting.cancel()
            failures[futures[future]] = outcome.error
    return failures[min(failures)] if failures else None
