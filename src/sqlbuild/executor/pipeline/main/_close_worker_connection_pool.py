"""Public entry for closing the extra connections of concurrent workers."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.executor.pipeline._helpers.connections import close_connections


def close_worker_connection_pool(
    *, adapter: BaseAdapter, connections: tuple[Any, ...], active_error: BaseException | None
) -> None:
    """Close every connection, raising a close failure only when no error is already active."""

    _ = close_connections(adapter=adapter, connections=connections, active_error=active_error)
