from __future__ import annotations

from collections.abc import Iterator

import pytest

import sqlbuild.runtime.contracts.main.open_connection as open_connection_module
from sqlbuild.runtime.contracts.main.open_connection import open_connection_with_hooks
from sqlbuild.runtime.contracts.models import ConnectionHooks
from tests.unit.src.sqlbuild.runtime.contracts._test_types import (
    OpenConnectionFailureTestCase,
    OpenConnectionSuccessTestCase,
)
from tests.unit.src.sqlbuild.runtime.contracts.helpers import (
    FailingConnectionAdapter,
    RecordingConnectionAdapter,
)


@pytest.mark.parametrize(
    "test_case",
    [
        OpenConnectionSuccessTestCase(
            description="successful connection reports start then completion",
            connection_config={"database": "analytics.duckdb", "read_only": True},
            monotonic_times=(10.0, 10.75),
            expected_event_order=("start", "connect", "complete"),
            expected_elapsed_seconds=0.75,
            expected_connection_count=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_connection_hooks_when_opening_succeeds_then_reports_order_and_elapsed_time(
    test_case: OpenConnectionSuccessTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    reported_elapsed_seconds: list[float] = []
    connection_counts: list[int] = []
    connection: object = object()
    adapter: RecordingConnectionAdapter = RecordingConnectionAdapter(
        events=events,
        connection=connection,
    )
    monotonic_times: Iterator[float] = iter(test_case.monotonic_times)
    monkeypatch.setattr(open_connection_module.time, "monotonic", lambda: next(monotonic_times))

    def on_start(connection_count: int) -> None:
        events.append("start")
        connection_counts.append(connection_count)

    def on_complete(connection_count: int, *, elapsed_seconds: int | float) -> None:
        events.append("complete")
        connection_counts.append(connection_count)
        reported_elapsed_seconds.append(float(elapsed_seconds))

    result: object = open_connection_with_hooks(
        adapter=adapter,
        connection_config=test_case.connection_config,
        hooks=ConnectionHooks(
            on_connection_start=on_start,
            on_connection_complete=on_complete,
        ),
    )

    assert result is connection
    assert adapter.connected_config is test_case.connection_config
    assert tuple(events) == test_case.expected_event_order
    assert reported_elapsed_seconds == [test_case.expected_elapsed_seconds]
    assert connection_counts == [test_case.expected_connection_count] * 2


@pytest.mark.parametrize(
    "test_case",
    [
        OpenConnectionFailureTestCase(
            description="failed connection reports the original exception",
            connection_config={"database": "unavailable.duckdb"},
            monotonic_times=(20.0, 21.25),
            expected_error=RuntimeError("connection unavailable"),
            expected_event_order=("start", "connect", "error"),
            expected_elapsed_seconds=1.25,
            expected_connection_count=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_connection_hooks_when_opening_fails_then_reports_error_and_reraises_identity(
    test_case: OpenConnectionFailureTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    elapsed_seconds_values: list[float] = []
    connection_counts: list[int] = []
    adapter: FailingConnectionAdapter = FailingConnectionAdapter(
        events=events,
        error=test_case.expected_error,
    )
    monotonic_times: Iterator[float] = iter(test_case.monotonic_times)
    monkeypatch.setattr(open_connection_module.time, "monotonic", lambda: next(monotonic_times))

    def on_start(connection_count: int) -> None:
        events.append("start")
        connection_counts.append(connection_count)

    def on_error(connection_count: int, *, elapsed_seconds: int | float) -> None:
        events.append("error")
        connection_counts.append(connection_count)
        elapsed_seconds_values.append(float(elapsed_seconds))

    with pytest.raises(type(test_case.expected_error)) as exc_info:
        open_connection_with_hooks(
            adapter=adapter,
            connection_config=test_case.connection_config,
            hooks=ConnectionHooks(
                on_connection_start=on_start,
                on_connection_error=on_error,
            ),
        )

    assert exc_info.value is test_case.expected_error
    assert adapter.connected_config is test_case.connection_config
    assert tuple(events) == test_case.expected_event_order
    assert elapsed_seconds_values == [test_case.expected_elapsed_seconds]
    assert connection_counts == [test_case.expected_connection_count] * 2
