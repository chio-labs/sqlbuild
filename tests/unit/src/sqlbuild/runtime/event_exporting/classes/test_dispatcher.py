from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from sqlbuild.observability import LifecycleEvent
from sqlbuild.runtime.event_exporting.classes.dispatcher import EventExporterDispatcher
from sqlbuild.runtime.event_exporting.models import BoundEventExporter, EventExportSummary
from tests.unit.src.sqlbuild.runtime.event_exporting.classes._test_types import (
    EventExporterDispatcherTestCase,
)
from tests.unit.src.sqlbuild.runtime.event_exporting.classes.helpers import lifecycle_event


@pytest.mark.parametrize(
    "test_case",
    (EventExporterDispatcherTestCase("off-thread delivery", 1),),
    ids=lambda case: case.description,
)
def test_given_slow_exporter_when_enqueuing_then_execution_thread_is_not_blocked(
    test_case: EventExporterDispatcherTestCase,
) -> None:
    release: threading.Event = threading.Event()
    entered: threading.Event = threading.Event()
    caller_thread: int = threading.get_ident()
    exporter_threads: list[int] = []

    def publish(*, event: LifecycleEvent) -> None:
        del event
        exporter_threads.append(threading.get_ident())
        entered.set()
        release.wait()

    dispatcher: EventExporterDispatcher = EventExporterDispatcher(
        exporters=(BoundEventExporter("publish", publish, {}),),
        invocation_timeout_seconds=0.2,
    )
    started: float = time.monotonic()
    dispatcher.enqueue(lifecycle_event())

    assert time.monotonic() - started < 0.05
    assert entered.wait(timeout=0.2)
    assert exporter_threads == [exporter_threads[0]]
    assert exporter_threads[0] != caller_thread
    release.set()
    assert dispatcher.shutdown().delivered == test_case.expected_delivered


@pytest.mark.parametrize(
    "test_case",
    (EventExporterDispatcherTestCase("failure isolation", 1),),
    ids=lambda case: case.description,
)
def test_given_multiple_exporters_when_one_fails_then_later_exporter_runs_in_order(
    test_case: EventExporterDispatcherTestCase,
) -> None:
    calls: list[str] = []

    def failing(*, event: LifecycleEvent) -> None:
        del event
        calls.append("first")
        raise RuntimeError("secret destination detail")

    def succeeding(*, event: LifecycleEvent) -> None:
        del event
        calls.append("second")

    dispatcher: EventExporterDispatcher = EventExporterDispatcher(
        exporters=(
            BoundEventExporter("first", failing, {}),
            BoundEventExporter("second", succeeding, {}),
        )
    )
    dispatcher.enqueue(lifecycle_event())

    summary: EventExportSummary = dispatcher.shutdown()

    assert calls == ["first", "second"]
    assert summary.delivered == test_case.expected_delivered
    assert summary.failed == 1


@pytest.mark.parametrize(
    "test_case",
    (EventExporterDispatcherTestCase("immutable event", 1),),
    ids=lambda case: case.description,
)
def test_given_exporter_mutation_attempt_when_delivering_then_event_remains_immutable(
    test_case: EventExporterDispatcherTestCase,
) -> None:
    observed_commands: list[object] = []

    def mutating(*, event: LifecycleEvent) -> None:
        event.payload["command"] = "changed"  # ty: ignore[invalid-assignment]

    def observing(*, event: LifecycleEvent) -> None:
        observed_commands.append(event.payload["command"])

    dispatcher: EventExporterDispatcher = EventExporterDispatcher(
        exporters=(
            BoundEventExporter("mutating", mutating, {}),
            BoundEventExporter("observing", observing, {}),
        )
    )
    dispatcher.enqueue(lifecycle_event())

    summary: EventExportSummary = dispatcher.shutdown()

    assert observed_commands == ["build"]
    assert summary.failed == 1
    assert summary.delivered == test_case.expected_delivered


@pytest.mark.parametrize(
    "test_case",
    (EventExporterDispatcherTestCase("bounded hung shutdown", 0),),
    ids=lambda case: case.description,
)
def test_given_hung_exporter_when_shutting_down_then_flush_is_bounded_and_threads_are_daemon(
    test_case: EventExporterDispatcherTestCase,
) -> None:
    blocker: threading.Event = threading.Event()

    def publish(*, event: LifecycleEvent) -> None:
        del event
        blocker.wait()

    dispatcher: EventExporterDispatcher = EventExporterDispatcher(
        exporters=(BoundEventExporter("hung", publish, {}),),
        shutdown_timeout_seconds=0.05,
        invocation_timeout_seconds=10.0,
    )
    dispatcher.enqueue(lifecycle_event())
    started: float = time.monotonic()

    summary: EventExportSummary = dispatcher.shutdown()

    assert time.monotonic() - started < 0.2
    assert summary.failed == 1
    assert summary.delivered == test_case.expected_delivered
    assert not dispatcher.thread.is_alive()
    exporter_threads_are_daemon: bool = all(
        map(
            lambda thread: thread.daemon,
            filter(
                lambda thread: thread.name.startswith("sqlbuild-event-exporter-"),
                threading.enumerate(),
            ),
        )
    )
    assert exporter_threads_are_daemon
    blocker.set()


@pytest.mark.parametrize(
    "test_case",
    (EventExporterDispatcherTestCase("bounded queue overflow", 1),),
    ids=lambda case: case.description,
)
def test_given_full_queue_when_enqueuing_then_overflow_is_counted_per_exporter(
    test_case: EventExporterDispatcherTestCase,
) -> None:
    release: threading.Event = threading.Event()

    def publish(*, event: LifecycleEvent) -> None:
        del event
        release.wait()

    dispatcher: EventExporterDispatcher = EventExporterDispatcher(
        exporters=(BoundEventExporter("publish", publish, {}),),
        queue_capacity=1,
        invocation_timeout_seconds=0.2,
    )
    for index in range(100):
        dispatcher.enqueue(lifecycle_event(index))
    time.sleep(0.02)
    release.set()

    summary: EventExportSummary = dispatcher.shutdown()

    assert summary.dropped > 0
    assert summary.delivered + summary.failed + summary.dropped == 100
    assert summary.delivered >= test_case.expected_delivered


@pytest.mark.parametrize(
    "test_case",
    (EventExporterDispatcherTestCase("last live invocation finalizes once", 0),),
    ids=lambda case: case.description,
)
def test_given_multiple_timed_out_invocations_when_registering_finalizer_then_last_return_runs_once(
    test_case: EventExporterDispatcherTestCase,
) -> None:
    first_entered: threading.Event = threading.Event()
    second_entered: threading.Event = threading.Event()
    first_release: threading.Event = threading.Event()
    second_release: threading.Event = threading.Event()
    finalized: threading.Event = threading.Event()
    finalizer_calls: list[str] = []

    def first(*, event: LifecycleEvent) -> None:
        del event
        first_entered.set()
        first_release.wait()

    def second(*, event: LifecycleEvent) -> None:
        del event
        second_entered.set()
        second_release.wait()

    dispatcher: EventExporterDispatcher = EventExporterDispatcher(
        exporters=(
            BoundEventExporter("first", first, {}),
            BoundEventExporter("second", second, {}),
        ),
        shutdown_timeout_seconds=0.1,
        invocation_timeout_seconds=0.02,
    )
    dispatcher.enqueue(lifecycle_event())
    assert first_entered.wait(timeout=0.2)
    assert second_entered.wait(timeout=0.2)
    summary: EventExportSummary = dispatcher.shutdown()

    def finalize() -> None:
        finalizer_calls.append("finalized")
        finalized.set()

    dispatcher.finalize_when_idle(finalize)
    first_release.set()
    assert not finalized.wait(timeout=0.02)
    second_release.set()

    assert finalized.wait(timeout=0.2)
    assert finalizer_calls == ["finalized"]
    assert summary.delivered == test_case.expected_delivered


@pytest.mark.parametrize(
    "test_case",
    (EventExporterDispatcherTestCase("blocked diagnostics do not block shutdown", 0),),
    ids=lambda case: case.description,
)
def test_given_blocked_failure_notification_when_shutting_down_then_summary_is_final_and_bounded(
    test_case: EventExporterDispatcherTestCase,
) -> None:
    failure_started: threading.Event = threading.Event()
    release_failure: threading.Event = threading.Event()
    summary_received: threading.Event = threading.Event()
    callback_summaries: list[EventExportSummary] = []

    def failing(*, event: LifecycleEvent) -> None:
        del event
        raise RuntimeError("sanitized")

    def failure_callback(_failure: object) -> None:
        failure_started.set()
        release_failure.wait()

    def summary_callback(summary: EventExportSummary) -> None:
        callback_summaries.append(summary)
        summary_received.set()

    dispatcher: EventExporterDispatcher = EventExporterDispatcher(
        exporters=(BoundEventExporter("failing", failing, {}),),
        failure_callback=failure_callback,
        summary_callback=summary_callback,
        shutdown_timeout_seconds=0.05,
    )
    dispatcher.enqueue(lifecycle_event())
    assert failure_started.wait(timeout=0.2)
    started: float = time.monotonic()

    summary: EventExportSummary = dispatcher.shutdown()

    assert time.monotonic() - started < 0.2
    assert not dispatcher.thread.is_alive()
    assert summary.failed == 1
    assert summary.delivered == test_case.expected_delivered
    notifier: threading.Thread | None = dispatcher.notification_thread
    assert notifier is not None
    assert notifier.daemon
    assert notifier.is_alive()
    release_failure.set()
    assert summary_received.wait(timeout=0.2)
    assert callback_summaries == [summary]


@pytest.mark.parametrize(
    "test_case",
    (EventExporterDispatcherTestCase("concurrent shutdown shares final summary", 0),),
    ids=lambda case: case.description,
)
def test_given_concurrent_shutdown_callers_when_dispatcher_stops_then_summary_is_cached_once(
    test_case: EventExporterDispatcherTestCase,
) -> None:
    callers_ready: threading.Barrier = threading.Barrier(2)
    summary_received: threading.Event = threading.Event()
    callback_summaries: list[EventExportSummary] = []

    def summary_callback(summary: EventExportSummary) -> None:
        callback_summaries.append(summary)
        summary_received.set()

    dispatcher: EventExporterDispatcher = EventExporterDispatcher(
        exporters=(),
        summary_callback=summary_callback,
    )

    def shutdown() -> EventExportSummary:
        _ = callers_ready.wait()
        return dispatcher.shutdown()

    with ThreadPoolExecutor(max_workers=2) as executor:
        summaries: tuple[EventExportSummary, ...] = tuple(
            executor.map(lambda _: shutdown(), range(2))
        )

    assert summaries[0] is summaries[1]
    assert summaries[0].delivered == test_case.expected_delivered
    assert summary_received.wait(timeout=0.2)
    assert callback_summaries == [summaries[0]]
