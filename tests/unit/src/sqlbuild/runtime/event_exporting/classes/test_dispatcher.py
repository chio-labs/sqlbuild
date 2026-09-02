from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import cast

import pytest

from sqlbuild.observability import LifecycleEvent
from sqlbuild.runtime.event_exporting.classes.dispatcher import EventExporterDispatcher
from sqlbuild.runtime.event_exporting.exceptions import EventExporterInputError
from sqlbuild.runtime.event_exporting.models import (
    BoundEventExporter,
    EventExporterCounts,
    EventExportSummary,
)
from tests.unit.src.sqlbuild.runtime.event_exporting.classes._test_types import (
    EventExporterDispatcherTestCase,
    HealthIntervalTestCase,
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
    assert summary.accepted == summary.delivered + summary.failed + summary.dropped
    assert tuple(item.exporter_name for item in summary.per_exporter) == ("first", "second")


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
    assert summary.flush_complete


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
    assert not summary.flush_complete
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
    assert summary.accepted == summary.delivered + summary.failed + summary.dropped == 100
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


@pytest.mark.parametrize(
    "test_case",
    (EventExporterDispatcherTestCase("prequeue filtering", 0),),
    ids=lambda case: case.description,
)
def test_given_exporter_specific_filters_when_enqueuing_then_filtering_precedes_capacity(
    test_case: EventExporterDispatcherTestCase,
) -> None:
    calls: list[str] = []

    def publish(*, event: LifecycleEvent) -> None:
        calls.append(event.event_type)

    dispatcher: EventExporterDispatcher = EventExporterDispatcher(
        exporters=(
            BoundEventExporter(
                "runs", publish, {}, event_kinds=frozenset({"run"}), min_severity="debug"
            ),
            BoundEventExporter(
                "errors",
                publish,
                {},
                event_kinds=frozenset({"invocation"}),
                min_severity="error",
            ),
        ),
        queue_capacity=1,
    )

    dispatcher.enqueue(lifecycle_event())
    summary: EventExportSummary = dispatcher.shutdown()

    assert len(calls) == test_case.expected_delivered
    assert summary.accepted == 0
    assert summary.filtered == 2
    assert summary.dropped == 0
    assert summary.flush_complete


@pytest.mark.parametrize(
    "test_case",
    (EventExporterDispatcherTestCase("mixed eligibility", 0),),
    ids=lambda case: case.description,
)
def test_given_mixed_eligible_fanout_when_exporters_disagree_then_counts_are_independent(
    test_case: EventExporterDispatcherTestCase,
) -> None:
    calls: list[str] = []

    def failing(*, event: LifecycleEvent) -> None:
        del event
        raise ValueError("must never reach diagnostics")

    def succeeding(*, event: LifecycleEvent) -> None:
        calls.append(event.event_type)

    dispatcher: EventExporterDispatcher = EventExporterDispatcher(
        exporters=(
            BoundEventExporter("failing", failing, {}),
            BoundEventExporter(
                "statement_only", succeeding, {}, event_kinds=frozenset({"statement"})
            ),
        )
    )
    dispatcher.enqueue(lifecycle_event())

    summary: EventExportSummary = dispatcher.shutdown()

    assert len(calls) == test_case.expected_delivered
    assert summary.accepted == 1
    assert summary.filtered == 1
    assert summary.failed == 1
    assert summary.per_exporter[0].counts.failed == 1
    assert summary.per_exporter[1].counts.filtered == 1


@pytest.mark.parametrize(
    "test_case",
    (EventExporterDispatcherTestCase("mixed displacement", 3),),
    ids=lambda case: case.description,
)
def test_given_mixed_eligible_queue_when_high_priority_displaces_then_attempts_count_once(
    test_case: EventExporterDispatcherTestCase,
) -> None:
    entered: threading.Event = threading.Event()
    release: threading.Event = threading.Event()
    calls: list[tuple[str, str]] = []

    def first(*, event: LifecycleEvent) -> None:
        calls.append(("first", event.event_type))
        entered.set()
        release.wait()

    def second(*, event: LifecycleEvent) -> None:
        calls.append(("second", event.event_type))

    dispatcher: EventExporterDispatcher = EventExporterDispatcher(
        exporters=(
            BoundEventExporter("first", first, {}),
            BoundEventExporter("second", second, {}, min_severity="info"),
        ),
        queue_capacity=1,
        invocation_timeout_seconds=1,
    )
    dispatcher.enqueue(lifecycle_event(1))
    assert entered.wait(timeout=0.2)
    dispatcher.enqueue(lifecycle_event(2))
    dispatcher.enqueue(lifecycle_event(3, "invocation_failed"))
    release.set()

    summary: EventExportSummary = dispatcher.shutdown()

    assert len(calls) == test_case.expected_delivered
    assert calls == [
        ("first", "invocation_started"),
        ("first", "invocation_failed"),
        ("second", "invocation_failed"),
    ]
    first_counts: EventExporterCounts = summary.per_exporter[0].counts
    second_counts: EventExporterCounts = summary.per_exporter[1].counts
    assert (first_counts.accepted, first_counts.delivered, first_counts.dropped) == (3, 2, 1)
    assert (second_counts.filtered, second_counts.accepted, second_counts.delivered) == (2, 1, 1)
    assert summary.accepted == summary.delivered + summary.failed + summary.dropped


@pytest.mark.parametrize(
    "test_case",
    (EventExporterDispatcherTestCase("producer stress", 400),),
    ids=lambda case: case.description,
)
def test_given_concurrent_producers_when_queue_overloads_then_final_counts_remain_bounded(
    test_case: EventExporterDispatcherTestCase,
) -> None:

    def publish(*, event: LifecycleEvent) -> None:
        del event

    dispatcher: EventExporterDispatcher = EventExporterDispatcher(
        exporters=(BoundEventExporter("publish", publish, {}),), queue_capacity=8
    )
    with ThreadPoolExecutor(max_workers=8) as executor:
        tuple(
            executor.map(
                lambda index: dispatcher.enqueue(lifecycle_event(index)),
                range(test_case.expected_delivered),
            )
        )

    summary: EventExportSummary = dispatcher.shutdown()

    assert summary.accepted == test_case.expected_delivered
    assert summary.accepted == summary.delivered + summary.failed + summary.dropped
    assert summary.queue_depth == 0
    assert summary.queue_capacity == 8
    assert summary.flush_complete


@pytest.mark.parametrize(
    "test_case",
    (EventExporterDispatcherTestCase("safe health", 1),),
    ids=lambda case: case.description,
)
def test_given_sensitive_exporter_exception_when_reporting_then_only_safe_dimensions_escape(
    test_case: EventExporterDispatcherTestCase,
) -> None:
    failures: list[object] = []

    def failing(*, event: LifecycleEvent) -> None:
        del event
        raise RuntimeError("password=secret sql=select-sensitive destination=broker")

    dispatcher: EventExporterDispatcher = EventExporterDispatcher(
        exporters=(BoundEventExporter("safe_name", failing, {}),),
        failure_callback=failures.append,
    )
    dispatcher.enqueue(lifecycle_event())
    dispatcher.shutdown()

    assert len(failures) == test_case.expected_delivered
    rendered: str = repr(failures[0])
    assert "RuntimeError" in rendered
    assert "safe_name" in rendered
    assert "invocation" in rendered
    assert "debug" in rendered
    assert "secret" not in rendered
    assert "select-sensitive" not in rendered
    assert "broker" not in rendered


@pytest.mark.parametrize(
    "test_case",
    (
        HealthIntervalTestCase("zero", 0.0, "positive and finite"),
        HealthIntervalTestCase("negative", -1.0, "positive and finite"),
        HealthIntervalTestCase("infinite", float("inf"), "positive and finite"),
        HealthIntervalTestCase("nan", float("nan"), "positive and finite"),
        HealthIntervalTestCase("boolean", True, "positive and finite"),
    ),
    ids=lambda case: case.description,
)
def test_given_invalid_health_interval_when_constructing_then_rejects(
    test_case: HealthIntervalTestCase,
) -> None:
    with pytest.raises(EventExporterInputError, match=test_case.expected_error):
        EventExporterDispatcher(health_interval_seconds=cast(float, test_case.interval))


@pytest.mark.parametrize(
    "test_case",
    (EventExporterDispatcherTestCase("live periodic filtering", 1),),
    ids=lambda case: case.description,
)
def test_given_live_accounting_change_when_interval_elapses_then_periodic_summary_is_published(
    test_case: EventExporterDispatcherTestCase,
) -> None:
    received: threading.Event = threading.Event()
    summaries: list[EventExportSummary] = []

    def summary_callback(summary: EventExportSummary) -> None:
        summaries.append(summary)
        received.set()

    dispatcher: EventExporterDispatcher = EventExporterDispatcher(
        exporters=(
            BoundEventExporter("runs", lambda *, event: None, {}, event_kinds=frozenset({"run"})),
        ),
        summary_callback=summary_callback,
        health_interval_seconds=0.01,
    )
    dispatcher.enqueue(lifecycle_event())

    assert received.wait(timeout=0.2)
    assert len(summaries) == test_case.expected_delivered
    assert summaries[0].filtered == 1
    assert not summaries[0].flush_complete
    dispatcher.shutdown()


@pytest.mark.parametrize(
    "test_case",
    (EventExporterDispatcherTestCase("coalesced periodic and retained final", 3),),
    ids=lambda case: case.description,
)
def test_given_blocked_notifier_when_health_changes_and_shutdown_then_newest_and_final_are_retained(
    test_case: EventExporterDispatcherTestCase,
) -> None:
    callback_entered: threading.Event = threading.Event()
    callback_release: threading.Event = threading.Event()
    callbacks_completed: threading.Semaphore = threading.Semaphore(0)
    summaries: list[EventExportSummary] = []

    def summary_callback(summary: EventExportSummary) -> None:
        summaries.append(summary)
        callback_entered.set()
        callback_release.wait()
        callbacks_completed.release()

    dispatcher: EventExporterDispatcher = EventExporterDispatcher(
        exporters=(
            BoundEventExporter("runs", lambda *, event: None, {}, event_kinds=frozenset({"run"})),
        ),
        summary_callback=summary_callback,
        health_interval_seconds=0.01,
    )
    dispatcher.enqueue(lifecycle_event(1))
    assert callback_entered.wait(timeout=0.2)
    dispatcher.enqueue(lifecycle_event(2))
    time.sleep(0.015)
    dispatcher.enqueue(lifecycle_event(3))
    time.sleep(0.03)

    final_summary: EventExportSummary = dispatcher.shutdown()
    assert summaries == [summaries[0]]
    callback_release.set()

    assert callbacks_completed.acquire(timeout=0.2)
    assert callbacks_completed.acquire(timeout=0.2)
    assert callbacks_completed.acquire(timeout=0.2)
    assert len(summaries) == test_case.expected_delivered
    assert [summary.filtered for summary in summaries] == [1, 3, 3]
    assert [summary.flush_complete for summary in summaries] == [False, False, True]
    assert summaries[-1] is final_summary


@pytest.mark.parametrize(
    "test_case",
    (EventExporterDispatcherTestCase("idle has final only", 1),),
    ids=lambda case: case.description,
)
def test_given_idle_dispatcher_when_intervals_repeat_then_no_duplicate_periodic_health_is_published(
    test_case: EventExporterDispatcherTestCase,
) -> None:
    final_received: threading.Event = threading.Event()
    summaries: list[EventExportSummary] = []

    def summary_callback(summary: EventExportSummary) -> None:
        summaries.append(summary)
        final_received.set()

    dispatcher: EventExporterDispatcher = EventExporterDispatcher(
        exporters=(), summary_callback=summary_callback, health_interval_seconds=0.01
    )
    time.sleep(0.04)
    assert summaries == []

    dispatcher.shutdown()

    assert final_received.wait(timeout=0.2)
    assert len(summaries) == test_case.expected_delivered
    assert summaries[0].flush_complete


@pytest.mark.parametrize(
    "test_case",
    (EventExporterDispatcherTestCase("health bypasses exporter", 1),),
    ids=lambda case: case.description,
)
def test_given_periodic_health_callback_when_published_then_it_never_reenters_exporter_queue(
    test_case: EventExporterDispatcherTestCase,
) -> None:
    periodic_received: threading.Event = threading.Event()
    summaries: list[EventExportSummary] = []
    exported: list[LifecycleEvent] = []

    def summary_callback(summary: EventExportSummary) -> None:
        summaries.append(summary)
        periodic_received.set()

    dispatcher: EventExporterDispatcher = EventExporterDispatcher(
        exporters=(BoundEventExporter("publish", lambda *, event: exported.append(event), {}),),
        summary_callback=summary_callback,
        health_interval_seconds=0.01,
    )
    dispatcher.enqueue(lifecycle_event())

    assert periodic_received.wait(timeout=0.2)
    assert len(exported) == test_case.expected_delivered
    assert summaries[0].accepted == 1
    dispatcher.shutdown()
