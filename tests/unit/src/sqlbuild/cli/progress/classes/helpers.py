"""Test helpers for native statement progress projection."""

from __future__ import annotations

from collections.abc import Callable
from io import StringIO
from threading import Event, Lock, Thread, current_thread

from sqlbuild.cli.progress.classes.native_progress_projector import NativeProgressProjector
from sqlbuild.observability import (
    EventDispatcher,
    OperationAttributes,
    OperationLifecycle,
    ResourceAttemptLifecycle,
    dispatcher_scope,
    invocation_scope,
    run_scope,
)
from sqlbuild.runtime.observability.classes.statement_lifecycle import StatementLifecycle
from sqlbuild.runtime.observability.classes.statement_monitor import StatementMonitor
from sqlbuild.runtime.observability.models import LifecycleEvent
from tests.unit.src.sqlbuild.cli.progress.classes._test_types import StatementProgressCase


class FakeSlowAdapter:
    """Block a fake statement until its first projected heartbeat."""

    def __init__(self, *, adapter: str, query_id: str | None) -> None:
        self.adapter: str = adapter
        self.query_id: str | None = None
        self._exposed_query_id: str | None = query_id
        self._release: Event = Event()
        self.monitor_thread: Thread | None = None

    def consume(self, event: LifecycleEvent) -> None:
        handlers: dict[str, Callable[[LifecycleEvent], None]] = {
            "statement_heartbeat": self._release_from_heartbeat
        }
        handlers.get(event.event_type, self._ignore_event)(event)

    def execute(self) -> None:
        with StatementLifecycle(
            adapter=self.adapter,
            sql="CREATE TABLE orders AS SELECT 1",
            intent="execute",
            query_id_provider=self.query_id_provider(),
            heartbeat_threshold_seconds=0.001,
            heartbeat_interval_seconds=0.001,
        ):
            self.query_id = self._exposed_query_id
            _ = self._release.wait(timeout=1.0)
            self.finish()

    def query_id_provider(self) -> Callable[[], str | None] | None:
        """Return the fake adapter's query-ID reader."""

        return lambda: self.query_id

    def finish(self) -> None:
        """Complete the fake warehouse execution successfully."""

    def _release_from_heartbeat(self, event: LifecycleEvent) -> None:
        del event
        self.monitor_thread = current_thread()
        self._release.set()

    @staticmethod
    def _ignore_event(event: LifecycleEvent) -> None:
        del event


class FakeFailingSlowAdapter(FakeSlowAdapter):
    """Fail after the fake warehouse statement's first heartbeat."""

    def finish(self) -> None:
        raise RuntimeError("warehouse statement failed")


class FakeSlowAdapterWithoutQueryIdProvider(FakeSlowAdapter):
    """Run heartbeats without installing a query-ID polling provider."""

    def query_id_provider(self) -> Callable[[], str | None] | None:
        return None


class RacingQueryIdProvider:
    """Hold the first provider call while detecting a concurrent second call."""

    def __init__(self, *, query_id: str) -> None:
        self.query_id: str = query_id
        self.first_entered: Event = Event()
        self.second_entered: Event = Event()
        self.release: Event = Event()
        self.call_count: int = 0
        self._lock: Lock = Lock()

    def __call__(self) -> str:
        with self._lock:
            self.call_count += 1
            call_count: int = self.call_count
        actions: dict[int, Callable[[], None]] = {1: self._hold_first_call}
        actions.get(call_count, self.second_entered.set)()
        return self.query_id

    def _hold_first_call(self) -> None:
        self.first_entered.set()
        _ = self.release.wait(timeout=1.0)


def execute_statement_progress_case(
    *, test_case: StatementProgressCase, adapter_type: type[FakeSlowAdapter]
) -> tuple[str, Thread, RuntimeError | None]:
    """Execute one fake resource-scoped statement and capture projected output."""

    stream: StringIO = StringIO()
    projector: NativeProgressProjector = NativeProgressProjector(stream=stream, use_color=False)
    adapter: FakeSlowAdapter = adapter_type(adapter=test_case.adapter, query_id=test_case.query_id)
    dispatcher: EventDispatcher = EventDispatcher()
    dispatcher.subscribe_lifecycle(subscriber=projector.consume, accepts_opaque=False)
    dispatcher.subscribe_lifecycle(subscriber=adapter.consume, accepts_opaque=False)
    error: RuntimeError | None = None
    try:
        with (
            invocation_scope("inv-statement-progress"),
            run_scope("run-statement-progress"),
            dispatcher_scope(dispatcher),
            ResourceAttemptLifecycle(
                resource_id="model:orders",
                resource_kind="table",
                resource_name="orders",
            ),
            OperationLifecycle(
                operation_kind="warehouse",
                operation_name="staging_creation",
                attributes=OperationAttributes(phase="create", adapter=test_case.adapter),
            ),
        ):
            adapter.execute()
    except RuntimeError as caught:
        error = caught
    monitor_thread: Thread = _required_monitor_thread(adapter.monitor_thread)
    return stream.getvalue(), monitor_thread, error


def _required_monitor_thread(thread: Thread | None) -> Thread:
    assert thread is not None
    return thread


def run_monitor_capture_race(*, query_id: str) -> tuple[tuple[str, ...], int, bool]:
    """Race monitor polling against stop and return publication diagnostics."""

    submissions: list[str] = []
    provider: RacingQueryIdProvider = RacingQueryIdProvider(query_id=query_id)
    monitor: StatementMonitor = StatementMonitor(
        on_submitted=submissions.append,
        on_heartbeat=lambda elapsed, current_query_id: None,
    )
    monitor.set_query_id_provider(provider)
    monitor.start()
    _ = provider.first_entered.wait(timeout=1.0)
    stopper: Thread = Thread(target=monitor.stop)
    stopper.start()
    _ = provider.second_entered.wait(timeout=0.05)
    provider.release.set()
    stopper.join(timeout=1.0)
    return tuple(submissions), provider.call_count, stopper.is_alive()
