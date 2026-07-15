"""Public operation for connection-backed worker completion."""

from __future__ import annotations

import queue
from collections.abc import Callable
from typing import Any

from sqlbuild.executor.contracts.types import WorkerFailureBuilder, WorkerSuccessBuilder
from sqlbuild.executor.scheduling._helpers.worker_completion import (
    run_worker_with_completion as _run_worker_with_completion,
)


def run_worker_with_completion[KeyT, ResultT, CompletionT](
    *,
    key: KeyT,
    connection_pool: queue.Queue[Any],
    completion_queue: queue.Queue[CompletionT],
    execute: Callable[[Any], ResultT],
    build_success: WorkerSuccessBuilder[KeyT, ResultT, CompletionT],
    build_failure: WorkerFailureBuilder[KeyT, CompletionT],
) -> None:
    """Execute work with one pooled connection and publish one completion."""

    return _run_worker_with_completion(
        key=key,
        connection_pool=connection_pool,
        completion_queue=completion_queue,
        execute=execute,
        build_success=build_success,
        build_failure=build_failure,
    )
