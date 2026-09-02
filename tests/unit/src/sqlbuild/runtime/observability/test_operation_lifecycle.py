from __future__ import annotations

from concurrent.futures import CancelledError, Future
from contextvars import Context, copy_context
from threading import Event, Thread
from typing import Any, cast

import pytest

from sqlbuild.observability import (
    EventDispatcher,
    ExecutionIdentity,
    LifecycleEvent,
    ObservabilityValidationError,
    OperationLifecycle,
    current_event_dispatcher,
    current_execution_identity,
    dispatcher_scope,
    invocation_scope,
    operation_scope,
    resource_attempt_scope,
    run_scope,
)
from sqlbuild.runtime.observability.classes.statement_lifecycle import StatementLifecycle
from tests.unit.src.sqlbuild.runtime.observability._test_types import OperationLifecycleCase


class _FailingSubscriber:
    def __call__(self, event: LifecycleEvent) -> None:
        del event
        raise SystemExit("subscriber secret")


class _ObservedContextManager:
    def __init__(self, events: list[LifecycleEvent]) -> None:
        self._events: list[LifecycleEvent] = events

    def __enter__(self) -> str:
        assert self._events[-1].event_type == "operation_started"
        return "context-value"

    def __exit__(self, *args: object) -> None:
        assert tuple(event.event_type for event in self._events) == ("operation_started",)


@pytest.mark.parametrize(
    "test_case",
    (
        OperationLifecycleCase(
            description="successful blocking callable",
            expected_event_types=("operation_started", "operation_completed"),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_blocking_callable_when_run_then_start_precedes_block_and_terminal_follows(
    test_case: OperationLifecycleCase,
) -> None:
    entered: Event = Event()
    release: Event = Event()
    events: list[LifecycleEvent] = []
    dispatcher: EventDispatcher = EventDispatcher()
    dispatcher.subscribe_lifecycle(subscriber=events.append, accepts_opaque=False)

    def block() -> str:
        entered.set()
        assert release.wait(timeout=5)
        return "exact-result"

    result: list[str] = []
    with invocation_scope("inv-callable"), dispatcher_scope(dispatcher):
        context: Context = copy_context()
        lifecycle: OperationLifecycle = OperationLifecycle(
            operation_kind="project", operation_name="project_compile"
        )
        thread: Thread = Thread(
            target=lambda: result.append(cast(str, context.run(lifecycle.run, block)))
        )
        thread.start()
        assert entered.wait(timeout=5)
        assert tuple(event.event_type for event in events) == ("operation_started",)
        release.set()
        thread.join(timeout=5)

    assert result == ["exact-result"]
    assert tuple(event.event_type for event in events) == test_case.expected_event_types
    assert cast(float, events[-1].payload["duration_ms"]) >= 0


@pytest.mark.parametrize(
    "test_case",
    (
        OperationLifecycleCase(
            description="successful iterator consumption",
            expected_event_types=("operation_started", "operation_completed"),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_iterator_when_consumed_then_terminal_follows_exhaustion(
    test_case: OperationLifecycleCase,
) -> None:
    events: list[LifecycleEvent] = []
    dispatcher: EventDispatcher = EventDispatcher()
    dispatcher.subscribe_lifecycle(subscriber=events.append, accepts_opaque=False)

    def values() -> Any:
        assert events[-1].event_type == "operation_started"
        yield 1
        assert tuple(event.event_type for event in events) == ("operation_started",)
        yield 2

    with invocation_scope("inv-iterator"), dispatcher_scope(dispatcher):
        result: tuple[int, ...] = OperationLifecycle(
            operation_kind="scenario", operation_name="scenario_capture"
        ).consume(values())

    assert result == (1, 2)
    assert tuple(event.event_type for event in events) == test_case.expected_event_types


@pytest.mark.parametrize(
    "test_case",
    (
        OperationLifecycleCase(
            description="context manager acquisition and use",
            expected_event_types=("operation_started", "operation_completed"),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_context_manager_when_operation_owns_use_then_terminal_follows_exit(
    test_case: OperationLifecycleCase,
) -> None:
    events: list[LifecycleEvent] = []
    dispatcher: EventDispatcher = EventDispatcher()
    dispatcher.subscribe_lifecycle(subscriber=events.append, accepts_opaque=False)

    with invocation_scope("inv-context"), dispatcher_scope(dispatcher):
        with OperationLifecycle(operation_kind="project", operation_name="project_compile"):
            with _ObservedContextManager(events) as value:
                assert value == "context-value"

    assert tuple(event.event_type for event in events) == test_case.expected_event_types


@pytest.mark.parametrize(
    "test_case",
    (
        OperationLifecycleCase(
            description="successful future result",
            expected_event_types=("operation_started", "operation_completed"),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_pending_future_when_result_owned_then_terminal_follows_result(
    test_case: OperationLifecycleCase,
) -> None:
    future: Future[str] = Future()
    events: list[LifecycleEvent] = []
    dispatcher: EventDispatcher = EventDispatcher()
    dispatcher.subscribe_lifecycle(subscriber=events.append, accepts_opaque=False)

    with invocation_scope("inv-future"), dispatcher_scope(dispatcher):
        context: Context = copy_context()
        result: list[str] = []
        lifecycle: OperationLifecycle = OperationLifecycle(
            operation_kind="python_node", operation_name="python_task"
        )
        thread: Thread = Thread(
            target=lambda: result.append(cast(str, context.run(lifecycle.result, future)))
        )
        thread.start()
        while not events:
            thread.join(timeout=0.001)
        assert tuple(event.event_type for event in events) == ("operation_started",)
        future.set_result("future-result")
        thread.join(timeout=5)

    assert result == ["future-result"]
    assert tuple(event.event_type for event in events) == test_case.expected_event_types


@pytest.mark.parametrize(
    "test_case",
    (
        OperationLifecycleCase(
            description="cancelled future result",
            expected_event_types=("operation_started", "operation_failed"),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_cancelled_future_when_result_owned_then_one_failure_is_published(
    test_case: OperationLifecycleCase,
) -> None:
    future: Future[str] = Future()
    _ = future.cancel()
    events: list[LifecycleEvent] = []
    dispatcher: EventDispatcher = EventDispatcher()
    dispatcher.subscribe_lifecycle(subscriber=events.append, accepts_opaque=False)

    with (
        invocation_scope("inv-cancelled-future"),
        dispatcher_scope(dispatcher),
        pytest.raises(CancelledError),
    ):
        _ = OperationLifecycle(operation_kind="python_node", operation_name="python_task").result(
            future
        )

    assert tuple(event.event_type for event in events) == test_case.expected_event_types
    assert events[-1].payload["error_type"] == "CancelledError"


@pytest.mark.parametrize(
    "test_case",
    (
        OperationLifecycleCase(
            description="base exception failure",
            expected_event_types=("operation_started", "operation_failed"),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_base_exception_when_operation_exits_then_one_safe_failure_is_published(
    test_case: OperationLifecycleCase,
) -> None:
    events: list[LifecycleEvent] = []
    dispatcher: EventDispatcher = EventDispatcher()
    dispatcher.subscribe_lifecycle(subscriber=events.append, accepts_opaque=False)

    with (
        invocation_scope("inv-system-exit"),
        dispatcher_scope(dispatcher),
        pytest.raises(SystemExit, match="private exit message"),
    ):
        with OperationLifecycle(operation_kind="subprocess", operation_name="dbt_command"):
            raise SystemExit("private exit message")

    assert tuple(event.event_type for event in events) == test_case.expected_event_types
    assert events[-1].payload["error_type"] == "SystemExit"
    assert "private exit message" not in repr(events)


@pytest.mark.parametrize(
    "test_case",
    (
        OperationLifecycleCase(
            description="subscriber-isolated operation",
            expected_event_types=("operation_started", "operation_completed"),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_failing_subscriber_when_operation_runs_then_exact_result_is_preserved(
    test_case: OperationLifecycleCase,
) -> None:
    events: list[LifecycleEvent] = []
    dispatcher: EventDispatcher = EventDispatcher()
    dispatcher.subscribe_lifecycle(subscriber=_FailingSubscriber(), accepts_opaque=False)
    dispatcher.subscribe_lifecycle(subscriber=events.append, accepts_opaque=False)
    expected: object = object()

    with invocation_scope("inv-subscriber"), dispatcher_scope(dispatcher):
        result: object = OperationLifecycle(
            operation_kind="loader", operation_name="external_source_load"
        ).run(lambda: expected)

    assert result is expected
    assert tuple(event.event_type for event in events) == test_case.expected_event_types


@pytest.mark.parametrize(
    "test_case",
    (
        OperationLifecycleCase(
            description="nested operation restoration",
            expected_event_types=("operation_started", "operation_completed"),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_nested_operations_when_exiting_then_parent_and_siblings_do_not_leak(
    test_case: OperationLifecycleCase,
) -> None:
    events: list[LifecycleEvent] = []
    dispatcher: EventDispatcher = EventDispatcher()
    dispatcher.subscribe_lifecycle(subscriber=events.append, accepts_opaque=False)

    with (
        invocation_scope("inv-nested"),
        run_scope("run-nested"),
        resource_attempt_scope(resource_id="resource", resource_attempt_id="attempt"),
        dispatcher_scope(dispatcher),
        operation_scope("parent-operation"),
    ):
        with OperationLifecycle(
            operation_kind="python_node",
            operation_name="python_task",
            operation_id="child-one",
        ):
            with StatementLifecycle(adapter="duckdb", sql="SELECT 1", intent="execute"):
                pass
        identity: ExecutionIdentity | None = current_execution_identity()
        assert identity is not None
        assert identity.operation_id == "parent-operation"
        with OperationLifecycle(
            operation_kind="python_node",
            operation_name="python_asset",
            operation_id="child-two",
        ):
            sibling_identity: ExecutionIdentity | None = current_execution_identity()
            assert sibling_identity is not None
            assert sibling_identity.operation_id == "child-two"

    statement_events: tuple[LifecycleEvent, ...] = tuple(
        filter(lambda event: event.event_type.startswith("statement_"), events)
    )
    assert {event.operation_id for event in statement_events} == {"child-one"}
    assert tuple(event.event_type for event in events[-2:]) == test_case.expected_event_types
    assert all(event.run_id == "run-nested" for event in events)
    assert all(event.resource_attempt_id == "attempt" for event in events)
    assert current_execution_identity() is None
    assert current_event_dispatcher() is None


@pytest.mark.parametrize(
    "test_case",
    (
        OperationLifecycleCase(
            description="direct transient operation",
            expected_event_types=("operation_started", "operation_completed"),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_direct_programmatic_use_when_complete_then_transient_context_is_restored(
    test_case: OperationLifecycleCase,
) -> None:
    result: str = OperationLifecycle(
        operation_kind="project", operation_name="project_discovery"
    ).run(lambda: "direct-result")

    assert result == "direct-result"
    assert test_case.expected_event_types[-1] == "operation_completed"
    assert current_execution_identity() is None
    assert current_event_dispatcher() is None


@pytest.mark.parametrize(
    "test_case",
    (
        OperationLifecycleCase(
            description="start factory failure without ambient context",
            expected_event_types=(),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_start_factory_base_exception_when_entering_then_transient_scopes_are_restored(
    test_case: OperationLifecycleCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lifecycle: OperationLifecycle = OperationLifecycle(
        operation_kind="project", operation_name="project_compile"
    )
    monkeypatch.setattr(
        "sqlbuild.runtime.observability.classes.operation_lifecycle.create_lifecycle_event",
        lambda **kwargs: (_ for _ in ()).throw(SystemExit("start factory failure")),
    )

    with pytest.raises(SystemExit, match="start factory failure"):
        _ = lifecycle.__enter__()

    assert test_case.expected_event_types == ()
    assert current_execution_identity() is None
    assert current_event_dispatcher() is None
    with pytest.raises(ObservabilityValidationError, match="cannot be entered more than once"):
        _ = lifecycle.__enter__()


@pytest.mark.parametrize(
    "test_case",
    (
        OperationLifecycleCase(
            description="start publication failure with ambient context",
            expected_event_types=(),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_start_publication_base_exception_when_nested_then_parent_context_is_restored(
    test_case: OperationLifecycleCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dispatcher: EventDispatcher = EventDispatcher()

    with invocation_scope("inv-parent"), dispatcher_scope(dispatcher):
        parent_identity: ExecutionIdentity | None = current_execution_identity()
        monkeypatch.setattr(
            OperationLifecycle,
            "_publish",
            lambda *args, **kwargs: (_ for _ in ()).throw(SystemExit("start publication failure")),
        )
        with pytest.raises(SystemExit, match="start publication failure"):
            with OperationLifecycle(operation_kind="project", operation_name="project_compile"):
                pass
        assert test_case.expected_event_types == ()
        assert current_execution_identity() is parent_identity
        assert current_event_dispatcher() is dispatcher
