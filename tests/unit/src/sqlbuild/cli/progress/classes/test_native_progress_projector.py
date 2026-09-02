from __future__ import annotations

from dataclasses import replace
from io import StringIO
from threading import Event, Thread
from typing import cast

import pytest

from sqlbuild.cli.progress.classes.native_progress_projector import NativeProgressProjector
from sqlbuild.observability import (
    EventDispatcher,
    LifecycleEvent,
    ResourceAttemptLifecycle,
    dispatcher_scope,
    invocation_scope,
    run_scope,
)
from tests.unit.src.sqlbuild.cli.progress.classes._test_types import (
    CursorCleanupCase,
    NativeProjectionCase,
    RetryProjectionCase,
    StartFlushCase,
)
from tests.unit.src.sqlbuild.runtime.observability.helpers import lifecycle_event


class _FlushRecordingStream(StringIO):
    def __init__(self, *, tty: bool = False) -> None:
        super().__init__()
        self.flush_count: int = 0
        self._tty: bool = tty

    def flush(self) -> None:
        self.flush_count += 1
        super().flush()

    def isatty(self) -> bool:
        return self._tty


@pytest.mark.parametrize(
    "test_case",
    (
        NativeProjectionCase(
            description="interleaved resource attempts and replayed facts",
            expected_lines=(
                "  2/2  loader    second START",
                "  1/2  table     first START",
                "Project compile  START",
                "Project compile  OK  (0.01s)",
            ),
            expected_first_duration_ms=1250.0,
            expected_second_duration_ms=2500.0,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_interleaved_and_duplicate_events_when_projected_then_ids_remain_independent(
    test_case: NativeProjectionCase,
) -> None:
    stream: _FlushRecordingStream = _FlushRecordingStream()
    projector: NativeProgressProjector = NativeProgressProjector(stream=stream, use_color=False)
    projector.configure_resources(ordinals={"first": 1, "second": 2}, total=2)
    second_start: LifecycleEvent = replace(
        lifecycle_event(
            "resource_attempt_started",
            run_id="run",
            resource_id="source:second",
            resource_attempt_id="attempt-second",
            payload={
                "resource_kind": "loader",
                "resource_name": "second",
                "attempt_number": 1,
            },
        ),
        event_id="second-start",
    )
    first_start: LifecycleEvent = replace(
        second_start,
        event_id="first-start",
        resource_id="model:first",
        resource_attempt_id="attempt-first",
        payload={
            "resource_kind": "table",
            "resource_name": "first",
            "attempt_number": 1,
        },
    )
    first_terminal: LifecycleEvent = replace(
        first_start,
        event_id="first-terminal",
        event_type="resource_attempt_completed",
        payload={**first_start.payload, "duration_ms": test_case.expected_first_duration_ms},
    )
    second_terminal: LifecycleEvent = replace(
        second_start,
        event_id="second-terminal",
        event_type="resource_attempt_completed",
        payload={**second_start.payload, "duration_ms": test_case.expected_second_duration_ms},
    )
    operation_start: LifecycleEvent = replace(
        lifecycle_event(
            "operation_started",
            operation_id="operation",
            payload={"operation_kind": "project", "operation_name": "project_compile"},
        ),
        event_id="operation-start",
    )
    operation_terminal: LifecycleEvent = replace(
        operation_start,
        event_id="operation-terminal",
        event_type="operation_completed",
        payload={**operation_start.payload, "duration_ms": 10.0},
    )
    statement: LifecycleEvent = replace(
        lifecycle_event(
            "statement_started",
            statement_id="statement",
            payload={"adapter": "duckdb", "statement_kind": "select"},
        ),
        event_id="statement-start",
    )

    for event in (
        second_start,
        first_start,
        first_start,
        first_terminal,
        second_terminal,
        statement,
        operation_start,
        operation_terminal,
    ):
        projector.consume(event)

    assert tuple(stream.getvalue().splitlines()) == test_case.expected_lines
    assert (
        projector.consume_resource_terminal(resource_name="first")
        == test_case.expected_first_duration_ms
    )
    assert (
        projector.consume_resource_terminal(resource_name="second")
        == test_case.expected_second_duration_ms
    )
    assert projector.consume_resource_terminal(resource_name="first") is None


@pytest.mark.parametrize(
    "test_case",
    (
        RetryProjectionCase(
            description="failed retry followed by successful final attempt",
            expected_lines=(
                "  1/2  task      orders START",
                "  2/2  task      inventory START",
                "  task      orders FAIL 0.10s",
                "  1/2  task      orders START",
                "  task      inventory OK 0.30s  rich",
                "  task      orders OK 0.25s  rich",
            ),
            expected_unrelated_duration_ms=300.0,
            expected_final_duration_ms=250.0,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_retried_resource_when_final_result_claims_then_prior_attempt_renders_first(
    test_case: RetryProjectionCase,
) -> None:
    stream: _FlushRecordingStream = _FlushRecordingStream()
    projector: NativeProgressProjector = NativeProgressProjector(stream=stream, use_color=False)
    projector.configure_resources(ordinals={"orders": 1, "inventory": 2}, total=2)
    first_start: LifecycleEvent = replace(
        lifecycle_event(
            "resource_attempt_started",
            run_id="run",
            resource_id="task:orders",
            resource_attempt_id="orders-attempt-1",
            payload={
                "resource_kind": "task",
                "resource_name": "orders",
                "attempt_number": 1,
            },
        ),
        event_id="orders-start-1",
    )
    first_failed: LifecycleEvent = replace(
        first_start,
        event_id="orders-failed-1",
        event_type="resource_attempt_failed",
        payload={**first_start.payload, "duration_ms": 100.0, "error_type": "TimeoutError"},
    )
    unrelated_start: LifecycleEvent = replace(
        first_start,
        event_id="inventory-start",
        resource_id="task:inventory",
        resource_attempt_id="inventory-attempt",
        payload={
            "resource_kind": "task",
            "resource_name": "inventory",
            "attempt_number": 1,
        },
    )
    unrelated_terminal: LifecycleEvent = replace(
        unrelated_start,
        event_id="inventory-terminal",
        event_type="resource_attempt_completed",
        payload={
            **unrelated_start.payload,
            "duration_ms": test_case.expected_unrelated_duration_ms,
        },
    )
    final_start: LifecycleEvent = replace(
        first_start,
        event_id="orders-start-2",
        resource_attempt_id="orders-attempt-2",
        payload={**first_start.payload, "attempt_number": 2},
    )
    final_terminal: LifecycleEvent = replace(
        final_start,
        event_id="orders-terminal-2",
        event_type="resource_attempt_completed",
        payload={**final_start.payload, "duration_ms": test_case.expected_final_duration_ms},
    )

    for event in (first_start, unrelated_start, first_failed, final_start, unrelated_terminal):
        projector.consume(event)
    unrelated_duration: float | None = projector.consume_resource_terminal(
        resource_name="inventory"
    )
    stream.write(
        f"  task      inventory OK {cast(float, unrelated_duration) / 1000.0:.2f}s  rich\n"
    )
    projector.consume(final_terminal)
    final_duration: float | None = projector.consume_resource_terminal(resource_name="orders")
    stream.write(f"  task      orders OK {cast(float, final_duration) / 1000.0:.2f}s  rich\n")
    projector.consume(first_failed)
    projector.consume(final_terminal)
    projector.close()

    assert unrelated_duration == test_case.expected_unrelated_duration_ms
    assert final_duration == test_case.expected_final_duration_ms
    assert tuple(stream.getvalue().splitlines()) == test_case.expected_lines


@pytest.mark.parametrize(
    "test_case",
    (
        RetryProjectionCase(
            description="same generic audit column on distinct targets",
            expected_lines=(
                "  1/1  audit     not_null (id) START",
                "  1/1  audit     not_null (id) START",
                "  orders audit OK 0.10s  rich",
                "  customers audit OK 0.20s  rich",
            ),
            expected_unrelated_duration_ms=100.0,
            expected_final_duration_ms=200.0,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_same_name_distinct_resources_when_claimed_by_id_then_terminals_do_not_cross(
    test_case: RetryProjectionCase,
) -> None:
    stream: _FlushRecordingStream = _FlushRecordingStream()
    projector: NativeProgressProjector = NativeProgressProjector(stream=stream, use_color=False)
    projector.configure_resources(ordinals={"not_null (id)": 1}, total=1)
    first_start: LifecycleEvent = replace(
        lifecycle_event(
            "resource_attempt_started",
            run_id="run",
            resource_id="audit:not_null:model:orders:id",
            resource_attempt_id="first-attempt",
            payload={
                "resource_kind": "audit",
                "resource_name": "not_null (id)",
                "attempt_number": 1,
            },
        ),
        event_id="first-start",
    )
    second_start: LifecycleEvent = replace(
        first_start,
        event_id="second-start",
        resource_id="audit:not_null:model:customers:id",
        resource_attempt_id="second-attempt",
    )
    first_terminal: LifecycleEvent = replace(
        first_start,
        event_id="first-terminal",
        event_type="resource_attempt_completed",
        payload={**first_start.payload, "duration_ms": test_case.expected_unrelated_duration_ms},
    )
    second_terminal: LifecycleEvent = replace(
        second_start,
        event_id="second-terminal",
        event_type="resource_attempt_completed",
        payload={**second_start.payload, "duration_ms": test_case.expected_final_duration_ms},
    )

    for event in (first_start, second_start, second_terminal, first_terminal):
        projector.consume(event)
    first_duration: float | None = projector.consume_resource_terminal(
        resource_name="not_null (id)", resource_id="audit:not_null:model:orders:id"
    )
    stream.write(f"  orders audit OK {cast(float, first_duration) / 1000.0:.2f}s  rich\n")
    second_duration: float | None = projector.consume_resource_terminal(
        resource_name="not_null (id)", resource_id="audit:not_null:model:customers:id"
    )
    stream.write(f"  customers audit OK {cast(float, second_duration) / 1000.0:.2f}s  rich\n")
    projector.close()

    assert first_duration == test_case.expected_unrelated_duration_ms
    assert second_duration == test_case.expected_final_duration_ms
    assert tuple(stream.getvalue().splitlines()) == test_case.expected_lines


@pytest.mark.parametrize(
    "test_case",
    (
        StartFlushCase(
            description="blocking resource starts after durable flushed row",
            expected_event_types=("resource_attempt_started", "resource_attempt_completed"),
            expected_flush_count_before_block=1,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_blocking_resource_when_entered_then_start_is_flushed_before_work(
    test_case: StartFlushCase,
) -> None:
    stream: _FlushRecordingStream = _FlushRecordingStream()
    projector: NativeProgressProjector = NativeProgressProjector(stream=stream, use_color=False)
    dispatcher: EventDispatcher = EventDispatcher()
    events: list[LifecycleEvent] = []
    dispatcher.subscribe_lifecycle(subscriber=projector.consume, accepts_opaque=False)
    dispatcher.subscribe_lifecycle(subscriber=events.append, accepts_opaque=False)
    entered: Event = Event()
    release: Event = Event()

    def block() -> None:
        assert stream.flush_count >= test_case.expected_flush_count_before_block
        assert stream.getvalue().endswith("source    orders START\n")
        entered.set()
        assert release.wait(timeout=5)

    def execute() -> None:
        with invocation_scope("inv"), run_scope("run"), dispatcher_scope(dispatcher):
            with ResourceAttemptLifecycle(
                resource_id="source:orders",
                resource_kind="source",
                resource_name="orders",
            ):
                block()

    thread: Thread = Thread(target=execute)
    thread.start()
    assert entered.wait(timeout=5)
    release.set()
    thread.join(timeout=5)

    assert tuple(event.event_type for event in events) == test_case.expected_event_types


@pytest.mark.parametrize(
    "test_case",
    (
        CursorCleanupCase(
            description="tty cleanup with missing terminal",
            expected_output="  table     abandoned START\n",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_missing_terminal_on_tty_when_closed_then_only_cursor_is_restored(
    test_case: CursorCleanupCase,
) -> None:
    stream: _FlushRecordingStream = _FlushRecordingStream(tty=True)
    projector: NativeProgressProjector = NativeProgressProjector(stream=stream, use_color=False)
    projector.consume(
        lifecycle_event(
            "resource_attempt_started",
            run_id="run",
            resource_id="model:abandoned",
            resource_attempt_id="attempt",
            payload={
                "resource_kind": "table",
                "resource_name": "abandoned",
                "attempt_number": 1,
            },
        )
    )

    projector.close()

    assert stream.getvalue() == test_case.expected_output
