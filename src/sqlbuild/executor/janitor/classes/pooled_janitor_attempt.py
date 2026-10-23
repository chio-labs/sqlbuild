"""One janitor action attempt on a connection borrowed from a worker pool."""

from __future__ import annotations

import queue
from collections.abc import Callable
from typing import Any

from sqlbuild.executor.janitor._helpers.worker_runs import attempt_janitor_action
from sqlbuild.executor.janitor.models import JanitorActionOutcome


class PooledJanitorAttempt[ResultT]:
    """Run an action on a borrowed connection and return the connection afterwards."""

    def __init__(self, *, action: Callable[..., ResultT], connections: queue.Queue[Any]) -> None:
        self._action: Callable[..., ResultT] = action
        self._connections: queue.Queue[Any] = connections

    def __call__(self, item: object) -> JanitorActionOutcome[ResultT]:
        borrowed: Any = self._connections.get()
        try:
            return attempt_janitor_action(action=self._action, item=item, connection=borrowed)
        finally:
            self._connections.put(borrowed)
