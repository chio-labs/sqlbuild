"""Bounded priority delivery of canonical lifecycle events."""

from __future__ import annotations

import math
import queue
import threading
import time
from collections.abc import Callable

from sqlbuild.observability import LifecycleEvent
from sqlbuild.runtime.event_exporting._helpers.sanitization import sanitized_exception_type
from sqlbuild.runtime.event_exporting.classes.finite_priority_event_queue import (
    FinitePriorityEventQueue,
)
from sqlbuild.runtime.event_exporting.classes.mutable_event_exporter_counts import (
    MutableEventExporterCounts,
)
from sqlbuild.runtime.event_exporting.constants import (
    DEFAULT_EVENT_EXPORT_HEALTH_INTERVAL_SECONDS,
    DEFAULT_EVENT_EXPORT_INVOCATION_TIMEOUT_SECONDS,
    DEFAULT_EVENT_EXPORT_NOTIFICATION_QUEUE_CAPACITY,
    DEFAULT_EVENT_EXPORT_QUEUE_CAPACITY,
    DEFAULT_EVENT_EXPORT_SHUTDOWN_TIMEOUT_SECONDS,
)
from sqlbuild.runtime.event_exporting.exceptions import (
    EventExporterInputError,
    EventExporterStateError,
)
from sqlbuild.runtime.event_exporting.main._lifecycle_export_policy import (
    lifecycle_export_policy,
)
from sqlbuild.runtime.event_exporting.main._severity_at_least import severity_at_least
from sqlbuild.runtime.event_exporting.models import (
    BoundEventExporter,
    EventExporterAccounting,
    EventExporterCounts,
    EventExporterFailure,
    EventExportSummary,
    LifecycleExportPolicy,
    QueuedLifecycleEvent,
)
from sqlbuild.runtime.output_capture.models import OutputRecord


class EventExporterDispatcher:
    """Deliver filtered lifecycle events off execution threads with bounded memory."""

    def __init__(
        self,
        *,
        exporters: tuple[BoundEventExporter, ...] | None = None,
        queue_capacity: int = DEFAULT_EVENT_EXPORT_QUEUE_CAPACITY,
        shutdown_timeout_seconds: float = DEFAULT_EVENT_EXPORT_SHUTDOWN_TIMEOUT_SECONDS,
        invocation_timeout_seconds: float = DEFAULT_EVENT_EXPORT_INVOCATION_TIMEOUT_SECONDS,
        notification_queue_capacity: int = DEFAULT_EVENT_EXPORT_NOTIFICATION_QUEUE_CAPACITY,
        health_interval_seconds: float = DEFAULT_EVENT_EXPORT_HEALTH_INTERVAL_SECONDS,
        failure_callback: Callable[[EventExporterFailure], object] | None = None,
        summary_callback: Callable[[EventExportSummary], object] | None = None,
    ) -> None:
        if notification_queue_capacity < 1:
            raise EventExporterInputError("event exporter queue capacities must be at least 1")
        if shutdown_timeout_seconds < 0 or invocation_timeout_seconds <= 0:
            raise EventExporterInputError("event exporter timeouts must be positive")
        if (
            isinstance(health_interval_seconds, bool)
            or not isinstance(health_interval_seconds, int | float)
            or not math.isfinite(health_interval_seconds)
            or health_interval_seconds <= 0
        ):
            raise EventExporterInputError(
                "event exporter health_interval_seconds must be positive and finite"
            )
        self._queue = FinitePriorityEventQueue(queue_capacity)
        self._exporters: tuple[BoundEventExporter, ...] = exporters or ()
        self._counts: list[MutableEventExporterCounts] = [
            MutableEventExporterCounts() for _ in self._exporters
        ]
        self._bound = threading.Event()
        if exporters is not None:
            self._bound.set()
        self._shutdown_timeout_seconds = shutdown_timeout_seconds
        self._invocation_timeout_seconds = invocation_timeout_seconds
        self._health_interval_seconds = float(health_interval_seconds)
        self._failure_callback = failure_callback
        self._summary_callback = summary_callback
        self._notification_queue: queue.Queue[EventExporterFailure] | None = (
            queue.Queue(maxsize=notification_queue_capacity)
            if failure_callback is not None or summary_callback is not None
            else None
        )
        self._lock = threading.Lock()
        self._notification_stopping = threading.Event()
        self._notification_wakeup = threading.Event()
        self._summary_notification_lock = threading.Lock()
        self._pending_periodic_summary: EventExportSummary | None = None
        self._periodic_inflight_signature: tuple[int, ...] | None = None
        self._final_notification_summary: EventExportSummary | None = None
        self._final_notification_delivered = False
        self._last_published_periodic_signature: tuple[int, ...] = (
            0,
            0,
            0,
            0,
            0,
            0,
            queue_capacity,
        )
        self._notification_thread: threading.Thread | None = None
        if self._notification_queue is not None:
            self._notification_thread = threading.Thread(
                target=self._run_notifications,
                name="sqlbuild-event-exporter-notifier",
                daemon=True,
            )
        self._health_stopping = threading.Event()
        self._health_thread: threading.Thread | None = None
        if summary_callback is not None:
            self._health_thread = threading.Thread(
                target=self._run_periodic_health,
                name="sqlbuild-event-exporter-health",
                daemon=True,
            )
        self._stopping = threading.Event()
        self._force_stop = threading.Event()
        self._accepting = True
        self._deadline: float | None = None
        self._blocked_exporters: set[int] = set()
        self._live_invocations: set[threading.Thread] = set()
        self._idle_finalizers: list[Callable[[], object]] = []
        self._dispatcher_running = True
        self._shutdown_started = False
        self._shutdown_complete = threading.Event()
        self._final_summary: EventExportSummary | None = None
        self._sequence = 0
        if self._notification_thread is not None:
            self._notification_thread.start()
        if self._health_thread is not None:
            self._health_thread.start()
        self._thread = threading.Thread(
            target=self._run, name="sqlbuild-event-exporter-dispatcher", daemon=True
        )
        self._thread.start()

    @property
    def thread(self) -> threading.Thread:
        return self._thread

    @property
    def notification_thread(self) -> threading.Thread | None:
        return self._notification_thread

    @property
    def health_thread(self) -> threading.Thread | None:
        return self._health_thread

    def enqueue(self, event: LifecycleEvent) -> None:
        """Filter and enqueue eligible exporter attempts without waiting."""

        policy: LifecycleExportPolicy = lifecycle_export_policy(event)
        with self._lock:
            if not self._bound.is_set():
                raise EventExporterStateError("event exporters must be bound before enqueue")
            eligible: list[int] = []
            for index, exporter in enumerate(self._exporters):
                if policy.kind not in exporter.event_kinds or not severity_at_least(
                    severity=policy.severity, minimum=exporter.min_severity
                ):
                    self._counts[index].filtered += 1
                else:
                    self._counts[index].accepted += 1
                    eligible.append(index)
            if not eligible:
                return
            if not self._accepting:
                self._drop_indices(tuple(eligible))
                return
            item: QueuedLifecycleEvent = QueuedLifecycleEvent(
                self._sequence, event, policy, tuple(eligible)
            )
            self._sequence += 1
            inserted, displaced = self._queue.put_nowait(item)
            if displaced is not None:
                self._drop_indices(displaced.eligible_exporters)
            if not inserted:
                self._drop_indices(item.eligible_exporters)

    def bind(self, exporters: tuple[BoundEventExporter, ...]) -> None:
        """Bind validated exporters once before lifecycle publication starts."""

        with self._lock:
            if self._bound.is_set():
                raise EventExporterStateError("event exporters are already bound")
            self._exporters = exporters
            self._counts = [MutableEventExporterCounts() for _ in exporters]
            self._bound.set()

    def export_output(self, records: tuple[OutputRecord, ...]) -> None:
        """Deliver output records through the already-bound destination providers."""

        invocation: threading.Thread = threading.current_thread()
        failed: bool = False
        with self._lock:
            self._live_invocations.add(invocation)
        try:
            for record in records:
                for exporter in self._exporters:
                    try:
                        exporter.function(event=record, **exporter.provider_arguments)
                    except BaseException:
                        failed = True
        finally:
            self._invocation_finished(invocation)
        if failed:
            raise EventExporterStateError("one or more output export attempts failed")

    def shutdown(self) -> EventExportSummary:
        """Stop acceptance and drain until the fixed shutdown deadline."""

        owns_shutdown = False
        with self._lock:
            if not self._shutdown_started:
                self._shutdown_started = True
                owns_shutdown = True
                self._accepting = False
                self._deadline = time.monotonic() + self._shutdown_timeout_seconds
                self._stopping.set()
                self._health_stopping.set()
            deadline: float = self._deadline or time.monotonic()
        if not owns_shutdown:
            self._shutdown_complete.wait()
            with self._lock:
                if self._final_summary is None:
                    raise EventExporterStateError(
                        "event exporter shutdown completed without summary"
                    )
                return self._final_summary
        self._thread.join(timeout=max(0.0, deadline - time.monotonic()) + 0.05)
        if self._thread.is_alive():
            self._force_stop.set()
            self._thread.join()
        with self._lock:
            summary: EventExportSummary = self._snapshot(final=True)
            self._final_summary = summary
        self._shutdown_complete.set()
        self._store_final_summary(summary)
        self._notification_stopping.set()
        self._notification_wakeup.set()
        return summary

    def finalize_when_idle(self, finalizer: Callable[[], object]) -> None:
        run_now = False
        with self._lock:
            if self._live_invocations or self._dispatcher_running:
                self._idle_finalizers.append(finalizer)
            else:
                run_now = True
        if run_now:
            self._run_finalizer(finalizer)

    def summary(self) -> EventExportSummary:
        """Return a thread-safe immutable point-in-time snapshot."""

        with self._lock:
            return self._snapshot(final=False)

    def _snapshot(self, *, final: bool) -> EventExportSummary:
        per_exporter: tuple[EventExporterAccounting, ...] = tuple(
            EventExporterAccounting(exporter.name, counts.freeze())
            for exporter, counts in zip(self._exporters, self._counts, strict=True)
        )
        aggregate: EventExporterCounts = EventExporterCounts(
            accepted=sum(item.counts.accepted for item in per_exporter),
            filtered=sum(item.counts.filtered for item in per_exporter),
            delivered=sum(item.counts.delivered for item in per_exporter),
            dropped=sum(item.counts.dropped for item in per_exporter),
            failed=sum(item.counts.failed for item in per_exporter),
        )
        flush_complete: bool = (
            final
            and not self._dispatcher_running
            and not self._live_invocations
            and len(self._queue) == 0
            and aggregate.accepted == aggregate.delivered + aggregate.failed + aggregate.dropped
        )
        return EventExportSummary(
            aggregate=aggregate,
            per_exporter=per_exporter,
            queue_depth=len(self._queue),
            queue_capacity=self._queue.capacity,
            flush_complete=flush_complete,
        )

    def _run(self) -> None:
        try:
            while not self._bound.wait(timeout=0.01):
                if self._stopping.is_set() or self._force_stop.is_set():
                    return
            while True:
                if self._past_deadline() or self._force_stop.is_set():
                    self._drop_queued_events()
                    return
                try:
                    item: QueuedLifecycleEvent = self._queue.get(timeout=0.01)
                except queue.Empty:
                    if self._stopping.is_set():
                        return
                    continue
                self._deliver(item)
        finally:
            self._dispatcher_finished()

    def _deliver(self, item: QueuedLifecycleEvent) -> None:
        for position, index in enumerate(item.eligible_exporters):
            if self._past_deadline():
                with self._lock:
                    self._drop_indices(item.eligible_exporters[position:])
                return
            if index in self._blocked_exporters:
                with self._lock:
                    self._counts[index].dropped += 1
                continue
            self._invoke(index=index, item=item)

    def _invoke(self, *, index: int, item: QueuedLifecycleEvent) -> None:
        exporter: BoundEventExporter = self._exporters[index]
        completed: threading.Event = threading.Event()
        failure_types: queue.SimpleQueue[str] = queue.SimpleQueue()

        def invoke() -> None:
            try:
                exporter.function(event=item.event, **exporter.provider_arguments)
            except BaseException as error:
                failure_types.put(sanitized_exception_type(error))
            finally:
                self._invocation_finished(threading.current_thread())
                completed.set()

        invocation: threading.Thread = threading.Thread(
            target=invoke, name=f"sqlbuild-event-exporter-{exporter.name}", daemon=True
        )
        with self._lock:
            self._live_invocations.add(invocation)
        try:
            invocation.start()
        except BaseException as error:
            self._invocation_finished(invocation)
            self._record_failure(
                index=index, policy=item.policy, error_type=sanitized_exception_type(error)
            )
            return
        if not self._wait_for_invocation(completed):
            self._blocked_exporters.add(index)
            self._record_failure(index=index, policy=item.policy, error_type="TimeoutError")
        elif not failure_types.empty():
            self._record_failure(index=index, policy=item.policy, error_type=failure_types.get())
        else:
            with self._lock:
                self._counts[index].delivered += 1

    def _wait_for_invocation(self, completed: threading.Event) -> bool:
        invocation_deadline: float = time.monotonic() + self._invocation_timeout_seconds
        while True:
            shutdown_deadline: float | None = self._deadline
            effective: float = min(invocation_deadline, shutdown_deadline or invocation_deadline)
            remaining: float = effective - time.monotonic()
            if remaining <= 0 or self._force_stop.is_set():
                return completed.is_set()
            if completed.wait(timeout=min(remaining, 0.01)):
                return True

    def _record_failure(
        self, *, index: int, policy: LifecycleExportPolicy, error_type: str
    ) -> None:
        with self._lock:
            self._counts[index].failed += 1
        self._enqueue_failure(
            EventExporterFailure(
                self._exporters[index].name, error_type, policy.kind, policy.severity
            )
        )

    def _drop_indices(self, indices: tuple[int, ...]) -> None:
        for index in indices:
            self._counts[index].dropped += 1

    def _drop_queued_events(self) -> None:
        items: tuple[QueuedLifecycleEvent, ...] = self._queue.drain()
        with self._lock:
            for item in items:
                self._drop_indices(item.eligible_exporters)

    def _enqueue_failure(self, notification: EventExporterFailure) -> None:
        if self._notification_queue is None:
            return
        if self._failure_callback is None:
            return
        try:
            self._notification_queue.put_nowait(notification)
        except queue.Full:
            return
        self._notification_wakeup.set()

    def _run_periodic_health(self) -> None:
        while not self._health_stopping.wait(timeout=self._health_interval_seconds):
            summary: EventExportSummary = self.summary()
            signature: tuple[int, ...] = self._health_signature(summary)
            with self._summary_notification_lock:
                if self._health_stopping.is_set() or self._final_notification_summary is not None:
                    return
                if signature in {
                    self._last_published_periodic_signature,
                    self._periodic_inflight_signature,
                }:
                    self._pending_periodic_summary = None
                    continue
                self._pending_periodic_summary = summary
            self._notification_wakeup.set()

    @staticmethod
    def _health_signature(summary: EventExportSummary) -> tuple[int, ...]:
        return (
            summary.accepted,
            summary.filtered,
            summary.delivered,
            summary.dropped,
            summary.failed,
            summary.queue_depth,
            summary.queue_capacity,
        )

    def _store_final_summary(self, summary: EventExportSummary) -> None:
        if self._summary_callback is None:
            return
        with self._summary_notification_lock:
            if self._final_notification_summary is None and not self._final_notification_delivered:
                self._final_notification_summary = summary
        self._notification_wakeup.set()

    def _take_periodic_summary(self) -> EventExportSummary | None:
        with self._summary_notification_lock:
            summary: EventExportSummary | None = self._pending_periodic_summary
            self._pending_periodic_summary = None
            self._periodic_inflight_signature = (
                None if summary is None else self._health_signature(summary)
            )
            return summary

    def _take_final_summary(self) -> EventExportSummary | None:
        with self._summary_notification_lock:
            if self._final_notification_delivered:
                return None
            return self._final_notification_summary

    def _mark_final_delivered(self) -> None:
        with self._summary_notification_lock:
            self._final_notification_delivered = True
            self._final_notification_summary = None

    def _mark_periodic_published(self, summary: EventExportSummary) -> None:
        with self._summary_notification_lock:
            self._last_published_periodic_signature = self._health_signature(summary)
            self._periodic_inflight_signature = None

    def _run_notifications(self) -> None:
        if self._notification_queue is None:
            return
        while True:
            self._notification_wakeup.clear()
            periodic_summary: EventExportSummary | None = self._take_periodic_summary()
            if periodic_summary is not None:
                try:
                    if self._summary_callback is not None:
                        self._summary_callback(periodic_summary)
                except BaseException:
                    pass
                finally:
                    self._mark_periodic_published(periodic_summary)
                continue
            final_summary: EventExportSummary | None = self._take_final_summary()
            if final_summary is not None:
                try:
                    if self._summary_callback is not None:
                        self._summary_callback(final_summary)
                except BaseException:
                    pass
                finally:
                    self._mark_final_delivered()
                return
            try:
                notification: EventExporterFailure = self._notification_queue.get_nowait()
            except queue.Empty:
                if self._notification_stopping.is_set():
                    return
                self._notification_wakeup.wait(timeout=0.01)
                continue
            try:
                if self._failure_callback is not None:
                    self._failure_callback(notification)
            except BaseException:
                pass
            finally:
                self._notification_queue.task_done()

    def _invocation_finished(self, invocation: threading.Thread) -> None:
        finalizers: tuple[Callable[[], object], ...] = ()
        with self._lock:
            self._live_invocations.discard(invocation)
            if (
                not self._live_invocations
                and not self._dispatcher_running
                and self._idle_finalizers
            ):
                finalizers = tuple(self._idle_finalizers)
                self._idle_finalizers.clear()
        for finalizer in finalizers:
            self._run_finalizer(finalizer)

    def _dispatcher_finished(self) -> None:
        finalizers: tuple[Callable[[], object], ...] = ()
        with self._lock:
            self._dispatcher_running = False
            if not self._live_invocations and self._idle_finalizers:
                finalizers = tuple(self._idle_finalizers)
                self._idle_finalizers.clear()
        for finalizer in finalizers:
            self._run_finalizer(finalizer)

    @staticmethod
    def _run_finalizer(finalizer: Callable[[], object]) -> None:
        try:
            finalizer()
        except BaseException:
            pass

    def _past_deadline(self) -> bool:
        return self._deadline is not None and time.monotonic() >= self._deadline
