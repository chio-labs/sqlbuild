"""A pool whose timed-out connection cannot be replaced keeps its slot and fails later work."""

from __future__ import annotations

import queue
import time
from typing import Any

import pytest

from sqlbuild.executor.scheduling.classes.recovering_connection_pool import (
    RecoveringConnectionPool,
)
from sqlbuild.executor.scheduling.main._run_worker import run_worker_with_completion
from sqlbuild.runtime.execution_limits.classes.connection_recovery import ConnectionRecovery
from tests.unit.src.sqlbuild.executor.scheduling.classes._test_types import (
    UnreplaceableConnectionTestCase,
)
from tests.unit.src.sqlbuild.executor.scheduling.classes.helpers import (
    LostConnectionAdapter,
    failure_completion,
    later_execute,
    success_completion,
    timed_out_execute,
)


@pytest.mark.parametrize(
    "test_case",
    [
        UnreplaceableConnectionTestCase(
            description="reconnect failure after a timeout keeps the slot and fails later items",
            later_items=2,
            expected_completions=(
                ("orders", "timed out"),
                ("customers", "failed: server closed the connection"),
                ("customers", "failed: server closed the connection"),
            ),
            expected_reconnect_attempts=3,
            expected_maximum_seconds=2.0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_unreplaceable_connection_when_returned_then_pool_keeps_it_and_later_items_fail(
    test_case: UnreplaceableConnectionTestCase,
) -> None:
    adapter: LostConnectionAdapter = LostConnectionAdapter()
    pool: RecoveringConnectionPool = RecoveringConnectionPool(
        recovery=ConnectionRecovery(adapter=adapter, connect=adapter.connect)
    )
    connection: object = object()
    pool.put(connection)
    completions: queue.Queue[tuple[str, str]] = queue.Queue()
    started: float = time.monotonic()

    run_worker_with_completion(
        key="orders",
        connection_pool=pool,
        completion_queue=completions,
        execute=timed_out_execute,
        build_success=success_completion,
        build_failure=failure_completion,
    )
    for _ in range(test_case.later_items):
        run_worker_with_completion(
            key="customers",
            connection_pool=pool,
            completion_queue=completions,
            execute=later_execute(adapter),
            build_success=success_completion,
            build_failure=failure_completion,
        )
    published: tuple[tuple[str, str], ...] = tuple(
        completions.get(timeout=1) for _ in test_case.expected_completions
    )
    returned: Any = pool.get(timeout=1)

    assert published == test_case.expected_completions
    assert returned is connection
    assert adapter.reconnect_attempts == test_case.expected_reconnect_attempts
    assert time.monotonic() - started < test_case.expected_maximum_seconds


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
