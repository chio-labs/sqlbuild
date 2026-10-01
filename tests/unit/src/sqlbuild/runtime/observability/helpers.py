"""Test builders for runtime observability contracts."""

import asyncio
import threading
import time
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from contextvars import Context, copy_context
from datetime import UTC, datetime
from threading import Lock
from types import MappingProxyType

import pytest

from sqlbuild.runtime.observability._helpers.dispatcher import dispatcher_scope
from sqlbuild.runtime.observability._helpers.factory import create_lifecycle_event
from sqlbuild.runtime.observability._helpers.identity import invocation_scope
from sqlbuild.runtime.observability.classes.event_dispatcher import EventDispatcher
from sqlbuild.runtime.observability.classes.microbatch_lifecycle import MicrobatchLifecycle
from sqlbuild.runtime.observability.classes.statement_lifecycle import StatementLifecycle
from sqlbuild.runtime.observability.classes.statement_monitor import StatementMonitor
from sqlbuild.runtime.observability.models import (
    DiagnosticLog,
    LifecycleEvent,
    MicrobatchLifecycleContext,
    OpaqueLifecycleEvent,
)
from sqlbuild.runtime.observability.types import JSONValue

OCCURRED_AT: datetime = datetime(2026, 8, 31, 12, 34, 56, 123456, tzinfo=UTC)


def capture_lifecycle_events() -> tuple[EventDispatcher, list[LifecycleEvent]]:
    events: list[LifecycleEvent] = []
    dispatcher: EventDispatcher = EventDispatcher()
    dispatcher.subscribe_lifecycle(subscriber=events.append, accepts_opaque=False)
    return dispatcher, events


def microbatch_lifecycle() -> MicrobatchLifecycle:
    return MicrobatchLifecycle(
        context=MicrobatchLifecycleContext(
            cursor_start="2026-01-01T00:00:00",
            cursor_end_exclusive="2026-01-02T00:00:00",
            planned_cursor_start="2026-01-01T00:00:00",
            planned_cursor_end_exclusive="2026-01-04T00:00:00",
            batch_index=1,
            batch_count=3,
            configured_batch_size="1d",
            effective_batch_size="1d",
            microbatch_strategy="watermark",
            microbatch_run_type="normal",
            batch_kind="ordinary",
        )
    )


async def delayed_statement(*, release: asyncio.Event, query_id: str) -> None:
    await release.wait()
    with StatementLifecycle(adapter="async", sql="SELECT delayed", intent="execute") as lifecycle:
        lifecycle.submitted(query_id=query_id)
        lifecycle.completed(query_id=query_id)


async def overlapping_statement(*, query_id: str) -> None:
    with StatementLifecycle(adapter="async", sql="SELECT overlap", intent="execute") as lifecycle:
        lifecycle.submitted(query_id=query_id)
        await asyncio.sleep(0)
        lifecycle.completed(query_id=query_id)


async def run_delayed_task_lifecycles(*, dispatcher: EventDispatcher, sql: str) -> None:
    release: asyncio.Event = asyncio.Event()
    with (
        invocation_scope("inv-delayed-task"),
        dispatcher_scope(dispatcher),
        StatementLifecycle(adapter="async", sql=sql, intent="execute"),
    ):
        child: asyncio.Task[None] = asyncio.create_task(
            delayed_statement(release=release, query_id="query-child")
        )
        await asyncio.sleep(0)
    release.set()
    await child


async def run_overlapping_task_lifecycles(*, dispatcher: EventDispatcher, sql: str) -> None:
    with (
        invocation_scope("inv-overlapping-tasks"),
        dispatcher_scope(dispatcher),
        StatementLifecycle(adapter="async", sql=sql, intent="execute"),
    ):
        await asyncio.gather(
            overlapping_statement(query_id="query-a"),
            overlapping_statement(query_id="query-b"),
        )


def run_copied_context_thread_statement() -> None:
    context: Context = copy_context()
    with ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(context.run, _thread_statement).result()


def _thread_statement() -> None:
    with StatementLifecycle(adapter="thread", sql="SELECT thread", intent="execute") as lifecycle:
        lifecycle.submitted(query_id="query-thread")
        lifecycle.completed(query_id="query-thread")


def publish_invocation_started(*, dispatcher: EventDispatcher) -> None:
    """Create and publish one invocation event for concurrent sequencing tests."""

    dispatcher.publish_lifecycle(create_lifecycle_event(event_type="invocation_started"))


def statement_event_types_by_id(
    events: list[LifecycleEvent],
) -> dict[str | None, tuple[str, ...]]:
    grouped: dict[str | None, list[str]] = {}
    for event in events:
        grouped.setdefault(event.statement_id, []).append(event.event_type)
    return {statement_id: tuple(event_types) for statement_id, event_types in grouped.items()}


class RecordingSubscriber:
    """Thread-safe recording subscriber for observability tests."""

    def __init__(self) -> None:
        self._lock: Lock = Lock()
        self._lifecycle: list[LifecycleEvent | OpaqueLifecycleEvent] = []
        self._diagnostics: list[DiagnosticLog] = []

    @property
    def lifecycle(self) -> tuple[LifecycleEvent | OpaqueLifecycleEvent, ...]:
        with self._lock:
            return tuple(self._lifecycle)

    @property
    def diagnostics(self) -> tuple[DiagnosticLog, ...]:
        with self._lock:
            return tuple(self._diagnostics)

    def record_lifecycle(self, event: LifecycleEvent | OpaqueLifecycleEvent) -> None:
        with self._lock:
            self._lifecycle.append(event)

    def record_known_lifecycle(self, event: LifecycleEvent) -> None:
        with self._lock:
            self._lifecycle.append(event)

    def record_diagnostic(self, log: DiagnosticLog) -> None:
        with self._lock:
            self._diagnostics.append(log)


class _UnprintableSubscriberError(BaseException):
    def __str__(self) -> str:
        raise SystemExit("exception formatting escaped")


class HostileSubscriber:
    """Subscriber whose name and raised exception cannot be formatted."""

    def __getattr__(self, name: str) -> object:
        raise SystemExit(f"subscriber naming escaped through {name}")

    def __call__(self, record: LifecycleEvent | DiagnosticLog) -> None:
        raise _UnprintableSubscriberError


def lifecycle_event(
    event_type: str = "invocation_started",
    *,
    run_id: str | None = None,
    resource_id: str | None = None,
    resource_attempt_id: str | None = None,
    operation_id: str | None = None,
    statement_id: str | None = None,
    occurred_at: datetime = OCCURRED_AT,
    payload: Mapping[str, JSONValue] = MappingProxyType({}),
) -> LifecycleEvent:
    """Build a valid known lifecycle event with deterministic values."""

    return LifecycleEvent(
        event_id="evt-1",
        event_type=event_type,
        schema_version=1,
        producer="sqlbuild",
        producer_version="0.72.1",
        occurred_at=occurred_at,
        invocation_id="inv-1",
        run_id=run_id,
        resource_id=resource_id,
        resource_attempt_id=resource_attempt_id,
        operation_id=operation_id,
        statement_id=statement_id,
        payload=payload,
    )


def diagnostic_log() -> DiagnosticLog:
    """Build a valid diagnostic log with deterministic values."""

    return DiagnosticLog(
        schema_version=1,
        producer="sqlbuild",
        producer_version="0.72.2",
        occurred_at=OCCURRED_AT,
        severity="info",
        logger="sqlbuild.test",
        source="test",
        message="diagnostic",
        invocation_id="inv-1",
    )


def count_monitor_thread_starts(*, monkeypatch: pytest.MonkeyPatch, statement_count: int) -> int:
    """Run fast statements without query-ID providers and count monitor threads started."""

    started: list[str] = []
    original_start: Callable[[threading.Thread], None] = threading.Thread.start

    def recording_start(thread: threading.Thread) -> None:
        started.append(thread.name)
        original_start(thread)

    monkeypatch.setattr(threading.Thread, "start", recording_start)
    dispatcher: EventDispatcher
    dispatcher, _ = capture_lifecycle_events()
    with invocation_scope("inv-fast-statements"), dispatcher_scope(dispatcher):
        for index in range(statement_count):
            with StatementLifecycle(adapter="duckdb", sql=f"SELECT {index}", intent="execute"):
                pass
    return started.count("sqlbuild-statement-monitor")


def submissions_after_late_provider(*, threshold_seconds: float, query_id: str) -> tuple[str, ...]:
    """Install a query-ID provider after a deferred start and return published submissions."""

    submitted: threading.Event = threading.Event()
    submissions: list[str] = []

    def record_submission(value: str) -> None:
        submissions.append(value)
        submitted.set()

    monitor: StatementMonitor = StatementMonitor(
        on_submitted=record_submission,
        on_heartbeat=lambda elapsed, current_query_id: None,
        threshold_seconds=threshold_seconds,
    )
    monitor.start()
    monitor.set_query_id_provider(lambda: query_id)
    _ = submitted.wait(timeout=5.0)
    _ = monitor.stop()
    return tuple(submissions)


def heartbeats_after_early_stop(*, threshold_seconds: float) -> int:
    """Stop a deferred monitor before its threshold and count heartbeats after the deadline."""

    heartbeats: list[float] = []
    monitor: StatementMonitor = StatementMonitor(
        on_submitted=lambda value: None,
        on_heartbeat=lambda elapsed, current_query_id: heartbeats.append(elapsed),
        threshold_seconds=threshold_seconds,
    )
    monitor.start()
    _ = monitor.stop()
    time.sleep(threshold_seconds * 4)
    return len(heartbeats)
