"""Public entry for opening the extra connections of concurrent workers."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.executor.pipeline._helpers.connections import open_worker_connections


def open_worker_connection_pool(
    *, adapter: BaseAdapter, connection_config: dict[str, object], connection_count: int
) -> tuple[Any, ...]:
    """Open `connection_count` connections concurrently, closing any opened when one fails."""

    return open_worker_connections(
        adapter=adapter, connection_config=connection_config, connection_count=connection_count
    )
