"""Thread-level serialization for node-result schema initialization."""

from __future__ import annotations

from collections.abc import Callable
from threading import Lock

_node_result_ddl_lock: Lock = Lock()


def run_with_node_result_ddl_lock(callback: Callable[[], None]) -> None:
    """Run node-result DDL under a process-local lock."""

    with _node_result_ddl_lock:
        callback()
