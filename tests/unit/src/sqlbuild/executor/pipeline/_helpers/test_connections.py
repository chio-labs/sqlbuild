from __future__ import annotations

import threading
from unittest.mock import Mock

import pytest

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.executor.build.models import BuildCallbacks
from sqlbuild.executor.pipeline._helpers import connections as connections_module
from sqlbuild.executor.pipeline._helpers.connections import (
    close_connections,
    open_worker_connections,
    prepare_build_connections,
)
from sqlbuild.executor.pipeline.models import BuildConnectionPreparation
from tests.unit.src.sqlbuild.executor.pipeline._helpers._test_types import (
    ConnectionPreparationTimingTestCase,
    WorkerConnectionTestCase,
)


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
        ConnectionPreparationTimingTestCase(
            description="connection and schema intervals are disjoint",
            clock_values=(0.0, 0.0, 5.0, 5.0, 7.0, 7.0, 10.0, 10.0),
            expected_connection_seconds=8.0,
            expected_schema_seconds=2.0,
            expected_total_seconds=10.0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_connection_and_schema_work_when_preparing_then_phase_intervals_do_not_overlap(
    test_case: ConnectionPreparationTimingTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monotonic: Mock = Mock(side_effect=test_case.clock_values)
    monkeypatch.setattr(connections_module.time, "monotonic", monotonic)
    monkeypatch.setattr(connections_module, "prepare_build_schemas", Mock())
    monkeypatch.setattr(
        connections_module, "open_worker_connections", Mock(return_value=(object(),))
    )

    preparation: BuildConnectionPreparation = prepare_build_connections(
        plan=PlanOutput(),
        adapter=Mock(connect=Mock(return_value=object())),
        connection_config={},
        connection_count=1,
        callbacks=BuildCallbacks(on_connection_complete=Mock()),
    )

    assert preparation.connection_seconds == test_case.expected_connection_seconds
    assert preparation.schema_seconds == test_case.expected_schema_seconds
    assert preparation.connection_seconds + (preparation.schema_seconds or 0) <= (
        test_case.expected_total_seconds
    )


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
    assert (
        len({id(connection) for connection in connections}) == test_case.expected_connection_count
    )
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
