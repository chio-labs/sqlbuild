"""Tests for shared worker completion helper."""

from __future__ import annotations

import queue
from collections.abc import Callable

import pytest

from sqlbuild.executor.scheduling.main._run_worker import run_worker_with_completion
from tests.unit.src.sqlbuild.executor.scheduling._helpers.worker_completion._test_types import (
    WorkerCompletionTestCase,
)
from tests.unit.src.sqlbuild.executor.scheduling._helpers.worker_completion.helpers import (
    build_connection_pool,
    build_failure_completion,
    build_success_completion,
    exceptional_execute,
    failing_execute,
    successful_execute,
)


@pytest.mark.parametrize(
    "test_case",
    [
        WorkerCompletionTestCase(
            description="publishes success completion and returns connection",
            key="node_a",
            connection="connection_a",
            execute=successful_execute("ok"),
            expected_completion=("node_a", "ok"),
            expected_connection="connection_a",
        ),
        WorkerCompletionTestCase(
            description="publishes failure completion and returns connection",
            key="node_b",
            connection="connection_b",
            execute=failing_execute("worker exploded"),
            expected_completion=("node_b", "worker exploded"),
            expected_connection="connection_b",
        ),
        WorkerCompletionTestCase(
            description="publishes completion for exceptional worker exit",
            key="node_c",
            connection="connection_c",
            execute=exceptional_execute("worker interrupted"),
            expected_completion=("node_c", "worker interrupted"),
            expected_connection="connection_c",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_worker_execution_when_running_with_completion_then_publishes_one_completion(
    test_case: WorkerCompletionTestCase,
) -> None:
    connection_pool: queue.Queue[str] = build_connection_pool(test_case.connection)
    completion_queue: queue.Queue[tuple[str, str]] = queue.Queue()
    execute: Callable[[object], str] = test_case.execute

    run_worker_with_completion(
        key=test_case.key,
        connection_pool=connection_pool,
        completion_queue=completion_queue,
        execute=execute,
        build_success=build_success_completion,
        build_failure=build_failure_completion,
    )

    assert completion_queue.get_nowait() == test_case.expected_completion
    assert completion_queue.empty()
    assert connection_pool.get_nowait() == test_case.expected_connection
