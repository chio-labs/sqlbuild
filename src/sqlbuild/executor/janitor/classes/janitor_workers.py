"""Bounded concurrent janitor actions, one warehouse connection per worker."""

from __future__ import annotations

import queue
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from sqlbuild.executor.janitor._helpers.worker_runs import attempt_janitor_action
from sqlbuild.executor.janitor.classes.janitor_chunk_collector import JanitorChunkCollector
from sqlbuild.executor.janitor.classes.pooled_janitor_attempt import PooledJanitorAttempt


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
        action: Callable[..., ResultT],
        collector: JanitorChunkCollector[ResultT],
    ) -> None:
        """Run `action(item=, connection=)` per item into `collector` until it stops accepting."""

        if len(self.connections) == 1 or len(items) <= 1:
            self._run_in_order(items=items, action=action, collector=collector)
            return
        connections: queue.Queue[Any] = queue.Queue()
        connection: Any
        for connection in self.connections:
            connections.put(connection)
        pool: ThreadPoolExecutor = ThreadPoolExecutor(
            max_workers=min(len(self.connections), len(items))
        )
        try:
            collector.collect(
                pool=pool,
                items=items,
                attempt=PooledJanitorAttempt(action=action, connections=connections),
            )
        finally:
            pool.shutdown(wait=True, cancel_futures=True)

    def _run_in_order[ItemT, ResultT](
        self,
        *,
        items: Sequence[ItemT],
        action: Callable[..., ResultT],
        collector: JanitorChunkCollector[ResultT],
    ) -> None:
        index: int
        item: ItemT
        for index, item in enumerate(items):
            if not collector.accepting:
                return
            try:
                collector.record(
                    index=index,
                    outcome=attempt_janitor_action(
                        action=action, item=item, connection=self.connection
                    ),
                )
            except BaseException as error:
                collector.interrupt(error)
