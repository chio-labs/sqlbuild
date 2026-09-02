"""Test builders for runtime observability contracts."""

from collections.abc import Mapping
from datetime import UTC, datetime
from threading import Lock
from types import MappingProxyType

from sqlbuild.runtime.observability.models import (
    DiagnosticLog,
    LifecycleEvent,
    OpaqueLifecycleEvent,
)
from sqlbuild.runtime.observability.types import JSONValue

OCCURRED_AT: datetime = datetime(2026, 8, 31, 12, 34, 56, 123456, tzinfo=UTC)


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


class _UnprintableSubscriberError(RuntimeError):
    def __str__(self) -> str:
        raise RuntimeError("exception formatting failed")


class HostileSubscriber:
    """Subscriber whose name and raised exception cannot be formatted."""

    def __getattr__(self, name: str) -> object:
        raise RuntimeError("subscriber naming failed")

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
