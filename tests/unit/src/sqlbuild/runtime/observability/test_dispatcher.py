"""Tests for synchronous typed observability publication."""

from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import replace
from threading import Event
from typing import cast

import pytest

from sqlbuild.observability import (
    DiagnosticLog,
    DiagnosticSubscriber,
    DispatchFailure,
    EventDispatcher,
    HealthCallback,
    KnownLifecycleSubscriber,
    LifecycleEvent,
    ObservabilityValidationError,
    OpaqueLifecycleEvent,
    OpaqueLifecycleSubscriber,
    Unsubscribe,
)
from tests.unit.src.sqlbuild.runtime.observability._test_types import (
    BlockingDispatchCase,
    ConcurrentDispatchCase,
    DispatchCountCase,
    DispatchFailureCase,
    DispatchMutationCase,
    DispatchOrderCase,
    OpaqueDispatchCase,
    RecursiveHealthCase,
)
from tests.unit.src.sqlbuild.runtime.observability.helpers import (
    HostileSubscriber,
    RecordingSubscriber,
    diagnostic_log,
    lifecycle_event,
)


@pytest.mark.parametrize(
    "test_case",
    [DispatchCountCase("malformed known event", 0, 0)],
    ids=lambda case: case.description,
)
def test_given_malformed_known_event_when_constructing_then_no_subscriber_can_receive_it(
    test_case: DispatchCountCase,
) -> None:
    dispatcher: EventDispatcher = EventDispatcher()
    recorder: RecordingSubscriber = RecordingSubscriber()
    _ = dispatcher.subscribe_lifecycle(
        subscriber=recorder.record_known_lifecycle, accepts_opaque=False
    )

    with pytest.raises(ObservabilityValidationError, match="requires correlation field"):
        _ = replace(lifecycle_event(), event_type="run_started")

    assert len(recorder.lifecycle) == test_case.expected_lifecycle_count
    assert len(recorder.diagnostics) == test_case.expected_diagnostic_count


@pytest.mark.parametrize(
    "test_case",
    [DispatchCountCase("separate typed channels", 1, 1)],
    ids=lambda case: case.description,
)
def test_given_lifecycle_and_log_subscribers_when_publishing_then_channels_remain_separate(
    test_case: DispatchCountCase,
) -> None:
    dispatcher: EventDispatcher = EventDispatcher()
    recorder: RecordingSubscriber = RecordingSubscriber()
    _ = dispatcher.subscribe_lifecycle(
        subscriber=recorder.record_known_lifecycle, accepts_opaque=False
    )
    _ = dispatcher.subscribe_diagnostics(recorder.record_diagnostic)
    event: LifecycleEvent = lifecycle_event()
    log: DiagnosticLog = diagnostic_log()

    dispatcher.publish_lifecycle(event)
    dispatcher.publish_diagnostic(log)
    with pytest.raises(ObservabilityValidationError, match="requires LifecycleEvent"):
        dispatcher.publish_lifecycle(log)  # ty: ignore[invalid-argument-type]
    with pytest.raises(ObservabilityValidationError, match="requires DiagnosticLog"):
        dispatcher.publish_diagnostic(event)  # ty: ignore[invalid-argument-type]

    assert recorder.lifecycle == (event,)
    assert recorder.diagnostics == (log,)
    assert len(recorder.lifecycle) == test_case.expected_lifecycle_count
    assert len(recorder.diagnostics) == test_case.expected_diagnostic_count


@pytest.mark.parametrize(
    "test_case",
    [
        OpaqueDispatchCase(
            description="unknown event name",
            raw={
                "event_id": "future-1",
                "event_type": "future_event",
                "schema_version": 1,
                "future_field": {"kept": True},
            },
            expected_typed_count=0,
            expected_opaque_count=1,
        ),
        OpaqueDispatchCase(
            description="newer schema version",
            raw={
                "event_id": "future-2",
                "event_type": "invocation_started",
                "schema_version": 2,
                "future_field": ["kept"],
            },
            expected_typed_count=0,
            expected_opaque_count=1,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_opaque_opt_in_when_publishing_unknown_event_then_only_opted_subscriber_gets_intact(
    test_case: OpaqueDispatchCase,
) -> None:
    dispatcher: EventDispatcher = EventDispatcher()
    typed: RecordingSubscriber = RecordingSubscriber()
    opaque: RecordingSubscriber = RecordingSubscriber()
    opaque_subscriber: OpaqueLifecycleSubscriber = opaque.record_lifecycle
    _ = dispatcher.subscribe_lifecycle(
        subscriber=typed.record_known_lifecycle, accepts_opaque=False
    )
    _ = dispatcher.subscribe_lifecycle(subscriber=opaque_subscriber, accepts_opaque=True)
    event: OpaqueLifecycleEvent = OpaqueLifecycleEvent(raw=test_case.raw)

    dispatcher.publish_lifecycle(event)

    assert len(typed.lifecycle) == test_case.expected_typed_count
    assert len(opaque.lifecycle) == test_case.expected_opaque_count
    assert opaque.lifecycle == (event,)


@pytest.mark.parametrize(
    "test_case",
    [
        DispatchOrderCase(
            description="registration and immediate nested order",
            expected_order=("first:outer", "first:nested", "second:nested", "second:outer"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_reentrant_subscriber_when_publishing_then_nested_snapshot_runs_immediately_in_order(
    test_case: DispatchOrderCase,
) -> None:
    dispatcher: EventDispatcher = EventDispatcher()
    observed: list[str] = []
    outer: LifecycleEvent = lifecycle_event()
    nested: LifecycleEvent = replace(outer, event_id="nested")
    labels: dict[str, str] = {outer.event_id: "outer", nested.event_id: "nested"}
    actions: dict[str, Callable[[], None]] = {
        outer.event_id: lambda: dispatcher.publish_lifecycle(nested),
        nested.event_id: lambda: None,
    }

    def first(event: LifecycleEvent) -> None:
        observed.append(f"first:{labels[event.event_id]}")
        actions[event.event_id]()

    def second(event: LifecycleEvent) -> None:
        observed.append(f"second:{labels[event.event_id]}")

    _ = dispatcher.subscribe_lifecycle(subscriber=first, accepts_opaque=False)
    _ = dispatcher.subscribe_lifecycle(subscriber=second, accepts_opaque=False)

    dispatcher.publish_lifecycle(outer)

    assert tuple(observed) == test_case.expected_order


@pytest.mark.parametrize(
    "test_case",
    [DispatchFailureCase("isolated failure and failing health callback", 1, 1, "lifecycle")],
    ids=lambda case: case.description,
)
def test_given_failing_subscriber_and_health_when_publishing_then_healthy_delivery_continues_once(
    test_case: DispatchFailureCase,
) -> None:
    health: list[DispatchFailure] = []
    healthy: RecordingSubscriber = RecordingSubscriber()

    def report(failure: DispatchFailure) -> None:
        health.append(failure)
        raise RuntimeError("health callback failed")

    health_callback: HealthCallback = report
    hostile: KnownLifecycleSubscriber = HostileSubscriber()
    dispatcher: EventDispatcher = EventDispatcher(health_callback=health_callback)
    _ = dispatcher.subscribe_lifecycle(subscriber=hostile, accepts_opaque=False)
    _ = dispatcher.subscribe_lifecycle(
        subscriber=healthy.record_known_lifecycle, accepts_opaque=False
    )

    dispatcher.publish_lifecycle(lifecycle_event())

    assert len(health) == test_case.expected_health_count
    assert len(healthy.lifecycle) == test_case.expected_healthy_count
    assert health[0].channel == test_case.expected_channel
    assert len(health[0].message) <= 512
    assert health[0].subscriber == "<unknown subscriber>"
    assert health[0].message == "<unprintable subscriber exception>"


@pytest.mark.parametrize(
    "test_case",
    [
        RecursiveHealthCase("recursive lifecycle health", "lifecycle", 1, 2),
        RecursiveHealthCase("recursive diagnostic health", "diagnostic", 1, 2),
    ],
    ids=lambda case: case.description,
)
def test_given_health_callback_republishes_failure_when_reporting_then_nested_report_is_suppressed(
    test_case: RecursiveHealthCase,
) -> None:
    health: list[DispatchFailure] = []
    healthy: RecordingSubscriber = RecordingSubscriber()
    publishers: dict[str, Callable[[], None]] = {}

    def report(failure: DispatchFailure) -> None:
        health.append(failure)
        publishers[test_case.channel]()

    def fail_lifecycle(event: LifecycleEvent) -> None:
        raise RuntimeError(f"lifecycle failure {event.event_id}")

    def fail_diagnostic(log: DiagnosticLog) -> None:
        raise RuntimeError(f"diagnostic failure {log.message}")

    health_callback: HealthCallback = report
    lifecycle_failure: KnownLifecycleSubscriber = fail_lifecycle
    diagnostic_failure: DiagnosticSubscriber = fail_diagnostic
    dispatcher: EventDispatcher = EventDispatcher(health_callback=health_callback)
    event: LifecycleEvent = lifecycle_event()
    log: DiagnosticLog = diagnostic_log()
    publishers.update(
        {
            "lifecycle": lambda: dispatcher.publish_lifecycle(event),
            "diagnostic": lambda: dispatcher.publish_diagnostic(log),
        }
    )
    register_failures: dict[str, Callable[[], Unsubscribe]] = {
        "lifecycle": lambda: dispatcher.subscribe_lifecycle(
            subscriber=lifecycle_failure, accepts_opaque=False
        ),
        "diagnostic": lambda: dispatcher.subscribe_diagnostics(diagnostic_failure),
    }
    register_healthy: dict[str, Callable[[], Unsubscribe]] = {
        "lifecycle": lambda: dispatcher.subscribe_lifecycle(
            subscriber=healthy.record_known_lifecycle, accepts_opaque=False
        ),
        "diagnostic": lambda: dispatcher.subscribe_diagnostics(healthy.record_diagnostic),
    }
    _ = register_failures[test_case.channel]()
    _ = register_healthy[test_case.channel]()

    publishers[test_case.channel]()

    assert len(health) == test_case.expected_health_count
    assert health[0].channel == test_case.channel
    assert len(healthy.lifecycle) + len(healthy.diagnostics) == test_case.expected_healthy_count


@pytest.mark.parametrize(
    "test_case",
    [
        DispatchMutationCase(
            description="snapshot mutation and idempotent cleanup",
            expected_first_publish=("first", "second"),
            expected_second_publish=("first", "third"),
            expected_after_cleanup=("third",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_callback_registration_changes_when_publishing_then_only_later_snapshot_changes(
    test_case: DispatchMutationCase,
) -> None:
    dispatcher: EventDispatcher = EventDispatcher()
    observed: list[str] = []
    second_unsubscribe: list[Unsubscribe] = []

    def third(event: LifecycleEvent) -> None:
        observed.append("third")

    def change_registration() -> None:
        second_unsubscribe[0]()
        second_unsubscribe[0]()
        _ = dispatcher.subscribe_lifecycle(subscriber=third, accepts_opaque=False)

    mutations: list[Callable[[], None]] = [change_registration, lambda: None]

    def first(event: LifecycleEvent) -> None:
        observed.append("first")
        mutations.pop(0)()

    def second(event: LifecycleEvent) -> None:
        observed.append("second")

    first_unsubscribe: Unsubscribe = dispatcher.subscribe_lifecycle(
        subscriber=first, accepts_opaque=False
    )
    second_unsubscribe.append(
        dispatcher.subscribe_lifecycle(subscriber=second, accepts_opaque=False)
    )

    dispatcher.publish_lifecycle(lifecycle_event())
    first_observed: tuple[str, ...] = tuple(observed)
    observed.clear()
    dispatcher.publish_lifecycle(lifecycle_event())
    first_unsubscribe()
    second_observed: tuple[str, ...] = tuple(observed)
    observed.clear()
    dispatcher.publish_lifecycle(lifecycle_event())

    assert first_observed == test_case.expected_first_publish
    assert second_observed == test_case.expected_second_publish
    assert tuple(observed) == test_case.expected_after_cleanup


@pytest.mark.parametrize(
    "test_case",
    [ConcurrentDispatchCase("concurrent producer snapshots", 4, 50, 200)],
    ids=lambda case: case.description,
)
def test_given_concurrent_publishers_when_recording_then_state_is_not_corrupted(
    test_case: ConcurrentDispatchCase,
) -> None:
    dispatcher: EventDispatcher = EventDispatcher()
    recorder: RecordingSubscriber = RecordingSubscriber()
    _ = dispatcher.subscribe_lifecycle(
        subscriber=recorder.record_known_lifecycle, accepts_opaque=False
    )

    def publish_batch(publisher: int) -> None:
        for index in range(test_case.events_per_publisher):
            dispatcher.publish_lifecycle(
                replace(lifecycle_event(), event_id=f"{publisher}-{index}")
            )

    with ThreadPoolExecutor(max_workers=test_case.publisher_count) as pool:
        futures: tuple[Future[None], ...] = tuple(
            pool.submit(publish_batch, publisher) for publisher in range(test_case.publisher_count)
        )
        for future in futures:
            future.result()

    known_events: tuple[LifecycleEvent, ...] = cast(tuple[LifecycleEvent, ...], recorder.lifecycle)
    observed_indexes: dict[int, list[int]] = {
        publisher: [] for publisher in range(test_case.publisher_count)
    }
    for event in known_events:
        publisher, index = event.event_id.split("-")
        observed_indexes[int(publisher)].append(int(index))
    expected_indexes: dict[int, list[int]] = {
        publisher: list(range(test_case.events_per_publisher))
        for publisher in range(test_case.publisher_count)
    }
    assert len(recorder.lifecycle) == test_case.expected_count
    assert len({event.event_id for event in known_events}) == test_case.expected_count
    assert observed_indexes == expected_indexes


@pytest.mark.parametrize(
    "test_case",
    [
        BlockingDispatchCase(
            "synchronous producer boundary",
            expected_before_release=("invocation_started",),
            expected_after_release=("invocation_started", "invocation_completed"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_blocking_callable_when_producing_then_started_precedes_entry_and_terminal_follows(
    test_case: BlockingDispatchCase,
) -> None:
    dispatcher: EventDispatcher = EventDispatcher()
    observed: list[str] = []
    entered: Event = Event()
    release: Event = Event()

    def record(event: LifecycleEvent) -> None:
        observed.append(event.event_type)

    def callable_body() -> None:
        entered.set()
        release.wait()

    def produce() -> None:
        dispatcher.publish_lifecycle(lifecycle_event())
        callable_body()
        dispatcher.publish_lifecycle(
            lifecycle_event("invocation_completed", payload={"command": "build", "exit_code": 0})
        )

    _ = dispatcher.subscribe_lifecycle(subscriber=record, accepts_opaque=False)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future: Future[None] = pool.submit(produce)
        assert entered.wait(timeout=5)
        assert tuple(observed) == test_case.expected_before_release
        release.set()
        future.result(timeout=5)

    assert tuple(observed) == test_case.expected_after_release


@pytest.mark.parametrize(
    "test_case",
    [DispatchCountCase("zero subscribers", 0, 0)],
    ids=lambda case: case.description,
)
def test_given_zero_subscribers_when_publishing_then_calls_complete_without_records(
    test_case: DispatchCountCase,
) -> None:
    dispatcher: EventDispatcher = EventDispatcher()

    dispatcher.publish_lifecycle(lifecycle_event())
    dispatcher.publish_diagnostic(diagnostic_log())

    assert test_case.expected_lifecycle_count == 0
    assert test_case.expected_diagnostic_count == 0
