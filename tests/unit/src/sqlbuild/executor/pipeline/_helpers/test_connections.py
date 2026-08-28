from __future__ import annotations

import threading

import pytest

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.executor.pipeline._helpers.connections import (
    close_connections,
    open_worker_connections,
)
from tests.unit.src.sqlbuild.executor.pipeline._helpers._test_types import WorkerConnectionTestCase


class _ConnectionAdapter(BaseAdapter):
    def __init__(self, *, fail_connect_index: int | None = None) -> None:
        self._lock: threading.Lock = threading.Lock()
        self._fail_connect_index: int | None = fail_connect_index
        self.connect_calls: list[dict[str, object]] = []
        self.close_attempts: list[object] = []

    def connect(self, config: dict[str, object]) -> object:
        with self._lock:
            call_index: int = len(self.connect_calls)
            self.connect_calls.append(config)
        if call_index == self._fail_connect_index:
            raise RuntimeError("original connection failure")
        return object()

    def close(self, connection: object) -> None:
        self.close_attempts.append(connection)
        if len(self.close_attempts) == 1:
            raise RuntimeError("close failure")

    def execute(self, connection: object, sql: str) -> object:
        del connection
        return sql


@pytest.mark.parametrize(
    "test_case",
    [
        WorkerConnectionTestCase(
            description="each worker opens an independent connection call",
            connection_count=3,
            expected_connection_count=3,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_worker_count_when_opening_connections_then_each_call_returns_independent_connection(
    test_case: WorkerConnectionTestCase,
) -> None:
    adapter: _ConnectionAdapter = _ConnectionAdapter()

    connections: tuple[object, ...] = open_worker_connections(
        adapter=adapter,
        connection_config={"authenticator": "oauth"},
        connection_count=test_case.connection_count,
    )

    assert len(connections) == test_case.expected_connection_count
    assert len({id(connection) for connection in connections}) == test_case.expected_connection_count
    assert len(adapter.connect_calls) == test_case.connection_count


@pytest.mark.parametrize(
    "test_case",
    [
        WorkerConnectionTestCase(
            description="partial connect failure attempts every successful close",
            connection_count=3,
            expected_connection_count=0,
            expected_close_attempts=2,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_partial_failure_when_opening_connections_then_cleanup_preserves_original_error(
    test_case: WorkerConnectionTestCase,
) -> None:
    adapter: _ConnectionAdapter = _ConnectionAdapter(fail_connect_index=1)

    with pytest.raises(RuntimeError, match="original connection failure"):
        open_worker_connections(
            adapter=adapter,
            connection_config={},
            connection_count=test_case.connection_count,
        )

    assert len(adapter.close_attempts) == test_case.expected_close_attempts


@pytest.mark.parametrize(
    "test_case",
    [
        WorkerConnectionTestCase(
            description="successful execution propagates first close failure after all attempts",
            connection_count=2,
            expected_connection_count=0,
            expected_close_attempts=2,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_no_active_error_when_closing_connections_then_propagates_close_failure(
    test_case: WorkerConnectionTestCase,
) -> None:
    adapter: _ConnectionAdapter = _ConnectionAdapter()

    with pytest.raises(RuntimeError, match="close failure"):
        close_connections(
            adapter=adapter,
            connections=tuple(object() for _ in range(test_case.connection_count)),
        )

    assert len(adapter.close_attempts) == test_case.expected_close_attempts


@pytest.mark.parametrize(
    "test_case",
    [
        WorkerConnectionTestCase(
            description="active execution error remains primary while all closes are attempted",
            connection_count=2,
            expected_connection_count=0,
            expected_close_attempts=2,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_active_error_when_closing_connections_then_preserves_original_error(
    test_case: WorkerConnectionTestCase,
) -> None:
    adapter: _ConnectionAdapter = _ConnectionAdapter()
    original_error: RuntimeError = RuntimeError("original execution failure")

    close_connections(
        adapter=adapter,
        connections=tuple(object() for _ in range(test_case.connection_count)),
        active_error=original_error,
    )
    with pytest.raises(RuntimeError, match="original execution failure") as raised:
        raise original_error

    assert raised.value is original_error
    assert len(adapter.close_attempts) == test_case.expected_close_attempts
