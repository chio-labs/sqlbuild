"""A worker connection pool that checks connections a deadline interrupted before reuse."""

from __future__ import annotations

import queue
from typing import Any

from sqlbuild.runtime.execution_limits.classes.connection_recovery import ConnectionRecovery


class RecoveringConnectionPool(queue.Queue[Any]):
    """Returns each connection to the pool healthy, replacing one a timeout left unusable."""

    def __init__(self, *, recovery: ConnectionRecovery) -> None:
        super().__init__()
        self._recovery: ConnectionRecovery = recovery

    def put(self, item: Any, block: bool = True, timeout: float | None = None) -> None:
        returned: Any = item
        try:
            returned = self._recovery.usable(item)
        finally:
            super().put(returned, block=block, timeout=timeout)
