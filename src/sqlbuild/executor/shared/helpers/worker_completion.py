"""Shared worker wrapper for connection-backed schedulers."""

from __future__ import annotations

import queue
from collections.abc import Callable
from typing import Any


def run_worker_with_completion[KeyT, ResultT, CompletionT](
    *,
    key: KeyT,
    connection_pool: queue.Queue[Any],
    completion_queue: queue.Queue[CompletionT],
    execute: Callable[[Any], ResultT],
    build_success: Callable[[KeyT, ResultT], CompletionT],
    build_failure: Callable[[KeyT, Exception], CompletionT],
) -> None:
    """Execute work with one pooled connection and always publish one completion."""

    connection: Any = connection_pool.get()
    try:
        try:
            result: ResultT = execute(connection)
        except Exception as exc:
            completion_queue.put(build_failure(key, exc))
        else:
            completion_queue.put(build_success(key, result))
    finally:
        connection_pool.put(connection)
