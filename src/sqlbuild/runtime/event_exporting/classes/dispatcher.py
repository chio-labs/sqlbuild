"""Bounded asynchronous delivery of canonical lifecycle events."""

from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable

from sqlbuild.observability import LifecycleEvent
from sqlbuild.runtime.event_exporting.constants import (
    DEFAULT_EVENT_EXPORT_INVOCATION_TIMEOUT_SECONDS,
    DEFAULT_EVENT_EXPORT_NOTIFICATION_QUEUE_CAPACITY,
    DEFAULT_EVENT_EXPORT_QUEUE_CAPACITY,
    DEFAULT_EVENT_EXPORT_SHUTDOWN_TIMEOUT_SECONDS,
)
from sqlbuild.runtime.event_exporting.exceptions import (
    EventExporterInputError,
    EventExporterStateError,
)
from sqlbuild.runtime.event_exporting.models import (
    BoundEventExporter,
    EventExporterFailure,
    EventExportSummary,
)


class EventExporterDispatcher:
    """Deliver events off execution threads with bounded memory and shutdown."""

    def __init__(
        self,
        *,
        exporters: tuple[BoundEventExporter, ...] | None = None,
        queue_capacity: int = DEFAULT_EVENT_EXPORT_QUEUE_CAPACITY,
        shutdown_timeout_seconds: float = DEFAULT_EVENT_EXPORT_SHUTDOWN_TIMEOUT_SECONDS,
        invocation_timeout_seconds: float = DEFAULT_EVENT_EXPORT_INVOCATION_TIMEOUT_SECONDS,
        notification_queue_capacity: int = DEFAULT_EVENT_EXPORT_NOTIFICATION_QUEUE_CAPACITY,
        failure_callback: Callable[[EventExporterFailure], object] | None = None,
        summary_callback: Callable[[EventExportSummary], object] | None = None,
    ) -> None:
        if queue_capacity < 1 or notification_queue_capacity < 1:
            raise EventExporterInputError("event exporter queue capacities must be at least 1")
        if shutdown_timeout_seconds < 0 or invocation_timeout_seconds <= 0:
            raise EventExporterInputError("event exporter timeouts must be positive")
        self._exporters: tuple[BoundEventExporter, ...] = exporters or ()
        self._bound = threading.Event()
        if exporters is not None:
            self._bound.set()
        self._queue: queue.Queue[LifecycleEvent] = queue.Queue(maxsize=queue_capacity)
        self._shutdown_timeout_seconds = shutdown_timeout_seconds
        self._invocation_timeout_seconds = invocation_timeout_seconds
        self._failure_callback = failure_callback
        self._summary_callback = summary_callback
        self._notification_queue: queue.Queue[EventExporterFailure | EventExportSummary] | None = (
            queue.Queue(maxsize=notification_queue_capacity)
            if failure_callback is not None or summary_callback is not None
            else None
        )
        self._notification_stopping = threading.Event()
        self._notification_thread: threading.Thread | None = None
        if self._notification_queue is not None:
            self._notification_thread = threading.Thread(
                target=self._run_notifications,
                name="sqlbuild-event-exporter-notifier",
                daemon=True,
            )
            self._notification_thread.start()
        self._lock = threading.Lock()
        self._stopping = threading.Event()
        self._force_stop = threading.Event()
        self._accepting = True
        self._deadline: float | None = None
        self._delivered = 0
        self._failed = 0
        self._dropped = 0
        self._unbound_dropped_events = 0
        self._blocked_exporters: set[str] = set()
        self._live_invocations: set[threading.Thread] = set()
        self._idle_finalizers: list[Callable[[], object]] = []
        self._dispatcher_running = True
        self._shutdown_started = False
        self._shutdown_complete = threading.Event()
        self._final_summary: EventExportSummary | None = None
        self._thread = threading.Thread(
            target=self._run,
            name="sqlbuild-event-exporter-dispatcher",
            daemon=True,
        )
        self._thread.start()

    @property
    def thread(self) -> threading.Thread:
        """Return the single framework dispatcher thread for lifecycle verification."""

        return self._thread

    @property
    def notification_thread(self) -> threading.Thread | None:
        """Return the optional best-effort notification worker."""

        return self._notification_thread

    def enqueue(self, event: LifecycleEvent) -> None:
        """Enqueue without waiting; overflow is accounted as dropped attempts."""

        with self._lock:
            if not self._accepting:
                self._dropped += len(self._exporters)
                return
            try:
                self._queue.put_nowait(event)
            except queue.Full:
                if self._bound.is_set():
                    self._dropped += len(self._exporters)
                else:
                    self._unbound_dropped_events += 1

    def bind(self, exporters: tuple[BoundEventExporter, ...]) -> None:
        """Bind validated exporters once, releasing buffered command events."""

        with self._lock:
            if self._bound.is_set():
                raise EventExporterStateError("event exporters are already bound")
            self._exporters = exporters
            self._dropped += self._unbound_dropped_events * len(exporters)
            self._unbound_dropped_events = 0
            self._bound.set()

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
            deadline: float = self._deadline or time.monotonic()
        if not owns_shutdown:
            self._shutdown_complete.wait()
            with self._lock:
                final_summary: EventExportSummary | None = self._final_summary
            if final_summary is None:
                raise EventExporterStateError("event exporter shutdown completed without summary")
            return final_summary
        self._thread.join(timeout=max(0.0, deadline - time.monotonic()) + 0.05)
        if self._thread.is_alive():
            self._force_stop.set()
            self._thread.join()
        summary: EventExportSummary = self.summary()
        with self._lock:
            self._final_summary = summary
        self._shutdown_complete.set()
        self._enqueue_notification(summary)
        self._notification_stopping.set()
        return summary

    def finalize_when_idle(self, finalizer: Callable[[], object]) -> None:
        """Run a one-shot finalizer now or after the last live invocation returns."""

        run_now = False
        with self._lock:
            if self._live_invocations or self._dispatcher_running:
                self._idle_finalizers.append(finalizer)
            else:
                run_now = True
        if run_now:
            self._run_finalizer(finalizer)

    def summary(self) -> EventExportSummary:
        """Return an atomic aggregate delivery snapshot."""

        with self._lock:
            return EventExportSummary(
                delivered=self._delivered,
                failed=self._failed,
                dropped=self._dropped,
            )

    def _run(self) -> None:
        try:
            self._run_until_stopped()
        finally:
            self._dispatcher_finished()

    def _run_until_stopped(self) -> None:
        while not self._bound.wait(timeout=0.01):
            if self._stopping.is_set() or self._force_stop.is_set():
                self._drop_queued_events()
                return
        while True:
            if self._past_deadline() or self._force_stop.is_set():
                self._drop_queued_events()
                return
            try:
                event: LifecycleEvent = self._queue.get(timeout=0.01)
            except queue.Empty:
                if self._stopping.is_set() or self._force_stop.is_set():
                    return
                continue
            try:
                self._deliver(event)
            finally:
                self._queue.task_done()

    def _deliver(self, event: LifecycleEvent) -> None:
        index: int
        exporter: BoundEventExporter
        for index, exporter in enumerate(self._exporters):
            if self._past_deadline():
                with self._lock:
                    self._dropped += len(self._exporters) - index
                return
            if exporter.name in self._blocked_exporters:
                with self._lock:
                    self._dropped += 1
                continue
            self._invoke(exporter=exporter, event=event)

    def _invoke(self, *, exporter: BoundEventExporter, event: LifecycleEvent) -> None:
        completed: threading.Event = threading.Event()
        failure_types: queue.SimpleQueue[str] = queue.SimpleQueue()

        def invoke() -> None:
            try:
                exporter.function(event=event, **exporter.provider_arguments)
            except BaseException as error:
                failure_types.put(type(error).__name__)
            finally:
                completed.set()
                self._invocation_finished(threading.current_thread())

        invocation: threading.Thread = threading.Thread(
            target=invoke,
            name=f"sqlbuild-event-exporter-{exporter.name}",
            daemon=True,
        )
        with self._lock:
            self._live_invocations.add(invocation)
        try:
            invocation.start()
        except BaseException:
            self._invocation_finished(invocation)
            raise
        if not self._wait_for_invocation(completed):
            self._blocked_exporters.add(exporter.name)
            self._record_failure(exporter_name=exporter.name, error_type="TimeoutError")
            return
        if not failure_types.empty():
            self._record_failure(exporter_name=exporter.name, error_type=failure_types.get())
            return
        with self._lock:
            self._delivered += 1

    def _wait_for_invocation(self, completed: threading.Event) -> bool:
        invocation_deadline: float = time.monotonic() + self._invocation_timeout_seconds
        while True:
            shutdown_deadline: float | None = self._deadline
            effective_deadline: float = (
                invocation_deadline
                if shutdown_deadline is None
                else min(invocation_deadline, shutdown_deadline)
            )
            remaining: float = effective_deadline - time.monotonic()
            if remaining <= 0 or self._force_stop.is_set():
                return completed.is_set()
            if completed.wait(timeout=min(remaining, 0.01)):
                return True

    def _record_failure(self, *, exporter_name: str, error_type: str) -> None:
        with self._lock:
            self._failed += 1
        self._enqueue_notification(EventExporterFailure(exporter_name, error_type))

    def _enqueue_notification(
        self, notification: EventExporterFailure | EventExportSummary
    ) -> None:
        notification_queue: queue.Queue[EventExporterFailure | EventExportSummary] | None = (
            self._notification_queue
        )
        if notification_queue is None:
            return
        if isinstance(notification, EventExporterFailure) and self._failure_callback is None:
            return
        if isinstance(notification, EventExportSummary) and self._summary_callback is None:
            return
        try:
            notification_queue.put_nowait(notification)
        except queue.Full:
            pass

    def _run_notifications(self) -> None:
        notification_queue: queue.Queue[EventExporterFailure | EventExportSummary] | None = (
            self._notification_queue
        )
        if notification_queue is None:
            return
        while True:
            try:
                notification: EventExporterFailure | EventExportSummary = notification_queue.get(
                    timeout=0.01
                )
            except queue.Empty:
                if self._notification_stopping.is_set():
                    return
                continue
            try:
                if isinstance(notification, EventExporterFailure):
                    failure_callback: Callable[[EventExporterFailure], object] | None = (
                        self._failure_callback
                    )
                    if failure_callback is not None:
                        _ = failure_callback(notification)
                else:
                    summary_callback: Callable[[EventExportSummary], object] | None = (
                        self._summary_callback
                    )
                    if summary_callback is not None:
                        _ = summary_callback(notification)
            except BaseException:
                pass
            finally:
                notification_queue.task_done()

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
            _ = finalizer()
        except BaseException:
            pass

    def _past_deadline(self) -> bool:
        deadline: float | None = self._deadline
        return deadline is not None and time.monotonic() >= deadline

    def _drop_queued_events(self) -> None:
        dropped_events = 0
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
            dropped_events += 1
            self._queue.task_done()
        if dropped_events:
            with self._lock:
                self._dropped += dropped_events * len(self._exporters)
