"""Callback-aware adapter connection opening."""

from __future__ import annotations

import time
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.runtime.contracts.models import ConnectionHooks


def open_connection_with_hooks(
    *,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    hooks: ConnectionHooks,
) -> Any:
    """Open one adapter connection and report its lifecycle through hooks."""

    if hooks.on_connection_start is not None:
        hooks.on_connection_start(1)
    started_at: float = time.monotonic()
    try:
        connection: Any = adapter.connect(connection_config)
    except Exception:
        if hooks.on_connection_error is not None:
            hooks.on_connection_error(1, elapsed_seconds=time.monotonic() - started_at)
        raise
    if hooks.on_connection_complete is not None:
        hooks.on_connection_complete(1, elapsed_seconds=time.monotonic() - started_at)
    return connection
