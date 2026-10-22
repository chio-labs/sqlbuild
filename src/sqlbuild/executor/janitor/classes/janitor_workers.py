"""Bounded concurrent janitor actions, one warehouse connection per worker."""

from __future__ import annotations

import queue
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from sqlbuild.executor.janitor._helpers.worker_runs import (
    attempt_janitor_action,
    collect_janitor_outcomes,
)
from sqlbuild.executor.janitor.classes.pooled_janitor_attempt import PooledJanitorAttempt
from sqlbuild.executor.janitor.models import JanitorActionOutcome, JanitorChunkOutcome


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
        on_done: Callable[..., None],
    ) -> JanitorChunkOutcome[ResultT]:
        """Run `action(item=, connection=)` per item until one fails, calling `on_done` per item."""

        if len(self.connections) == 1 or len(items) <= 1:
            return self._run_in_order(items=items, action=action, on_done=on_done)
        connections: queue.Queue[Any] = queue.Queue()
        connection: Any
        for connection in self.connections:
            connections.put(connection)
        pool: ThreadPoolExecutor = ThreadPoolExecutor(
            max_workers=min(len(self.connections), len(items))
        )
        try:
            return collect_janitor_outcomes(
                pool=pool,
                items=items,
                attempt=PooledJanitorAttempt(action=action, connections=connections),
                on_done=on_done,
            )
        finally:
            pool.shutdown(wait=True, cancel_futures=True)

    def _run_in_order[ItemT, ResultT](
        self,
        *,
        items: Sequence[ItemT],
        action: Callable[..., ResultT],
        on_done: Callable[..., None],
    ) -> JanitorChunkOutcome[ResultT]:
        outcomes: list[JanitorActionOutcome[ResultT] | None] = [None] * len(items)
        index: int
        item: ItemT
        for index, item in enumerate(items):
            outcome: JanitorActionOutcome[ResultT] = attempt_janitor_action(
                action=action, item=item, connection=self.connection
            )
            outcomes[index] = outcome
            on_done(index=index, outcome=outcome)
            if outcome.error is not None:
                break
        return JanitorChunkOutcome(outcomes=tuple(outcomes))
