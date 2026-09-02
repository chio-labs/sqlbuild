"""Test builders for runtime observability contracts."""

import asyncio
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from contextvars import Context, copy_context
from datetime import UTC, datetime
from threading import Lock
from types import MappingProxyType

from sqlbuild.runtime.observability._helpers.dispatcher import dispatcher_scope
from sqlbuild.runtime.observability._helpers.identity import invocation_scope
from sqlbuild.runtime.observability.classes.event_dispatcher import EventDispatcher
from sqlbuild.runtime.observability.classes.statement_lifecycle import StatementLifecycle
from sqlbuild.runtime.observability.models import (
    DiagnosticLog,
    LifecycleEvent,
    OpaqueLifecycleEvent,
)
from sqlbuild.runtime.observability.types import JSONValue

OCCURRED_AT: datetime = datetime(2026, 8, 31, 12, 34, 56, 123456, tzinfo=UTC)


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
