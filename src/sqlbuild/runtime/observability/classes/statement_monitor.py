"""Non-blocking monitor for an executing warehouse statement."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from contextvars import Context, copy_context

from sqlbuild.runtime.observability.classes.deferred_thread_starts import DeferredThreadStarts
from sqlbuild.runtime.observability.constants import STATEMENT_HEARTBEAT_THRESHOLD_SECONDS

_STATEMENT_QUERY_ID_POLL_SECONDS: float = 0.1
_DEFERRED_MONITOR_STARTS: DeferredThreadStarts = DeferredThreadStarts(
    name="sqlbuild-statement-monitor-starter"
)


class StatementMonitor:
    """Discover a query ID and emit bounded periodic heartbeats until stopped."""

    def __init__(
        self,
        *,
        on_submitted: Callable[[str], None],
        on_heartbeat: Callable[[float, str | None], None],
        threshold_seconds: float = STATEMENT_HEARTBEAT_THRESHOLD_SECONDS,
        interval_seconds: float | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._on_submitted: Callable[[str], None] = on_submitted
        self._on_heartbeat: Callable[[float, str | None], None] = on_heartbeat
        self._threshold_seconds: float = threshold_seconds
        self._interval_seconds: float = (
            threshold_seconds if interval_seconds is None else interval_seconds
        )
        self._clock: Callable[[], float] = clock
        self._started_at: float = clock()
        self._stop_event: threading.Event = threading.Event()
        self._provider_lock: threading.Lock = threading.Lock()
        self._wake_event: threading.Event = threading.Event()
        self._query_id_provider: Callable[[], str | None] | None = None
        self._query_id: str | None = None
        self._thread: threading.Thread | None = None
        self._thread_lock: threading.Lock = threading.Lock()
        self._context: Context | None = None
        self._stopped: bool = False
        self._deferred_start: int | None = None

    @property
    def query_id(self) -> str | None:
        """Return the latest warehouse query ID discovered by the monitor."""

        return self._query_id

    def start(self) -> None:
        """Monitor in a daemon thread, deferred to the first heartbeat without a query-ID poll."""

        self._context = copy_context()
        if self._has_query_id_provider() or self._threshold_seconds <= 0:
            self._start_thread()
            return
        self._deferred_start = _DEFERRED_MONITOR_STARTS.schedule(
            delay_seconds=self._threshold_seconds, start=self._start_thread
        )

    def set_query_id_provider(self, provider: Callable[[], str | None]) -> None:
        """Install a non-blocking adapter query-ID reader."""

        with self._provider_lock:
            self._query_id_provider = provider
        if self._context is not None:
            self._start_thread()
        self._wake_event.set()

    def stop(self) -> str | None:
        """Stop and join the monitor, returning any discovered query ID."""

        self._capture_query_id()
        self._stop_event.set()
        self._wake_event.set()
        with self._thread_lock:
            self._stopped = True
            self._context = None
            thread: threading.Thread | None = self._thread
            deferred_start: int | None = self._deferred_start
            self._deferred_start = None
        if deferred_start is not None:
            _DEFERRED_MONITOR_STARTS.cancel(deferred_start)
        if thread is not None and thread is not threading.current_thread():
            thread.join()
        self._release_callbacks()
        return self._query_id

    def _release_callbacks(self) -> None:
        """Drop references back to the statement so a stopped monitor retains nothing."""

        with self._provider_lock:
            self._query_id_provider = None
        self._on_submitted = lambda query_id: None
        self._on_heartbeat = lambda elapsed_seconds, query_id: None

    def _start_thread(self) -> None:
        with self._thread_lock:
            context: Context | None = self._context
            if self._stopped or self._thread is not None or context is None:
                return
            thread: threading.Thread = threading.Thread(
                target=context.run,
                args=(self._run,),
                name="sqlbuild-statement-monitor",
                daemon=True,
            )
            thread.start()
            self._thread = thread

    def _run(self) -> None:
        next_heartbeat: float = self._started_at + self._threshold_seconds
        while not self._stop_event.is_set():
            self._capture_query_id()
            now: float = self._clock()
            if now >= next_heartbeat:
                self._safe_heartbeat(elapsed_seconds=max(0.0, now - self._started_at))
                next_heartbeat = now + self._interval_seconds
            until_heartbeat: float = max(0.0, next_heartbeat - self._clock())
            wait_seconds: float = (
                min(_STATEMENT_QUERY_ID_POLL_SECONDS, until_heartbeat)
                if self._has_query_id_provider()
                else until_heartbeat
            )
            _ = self._wake_event.wait(wait_seconds)
            self._wake_event.clear()

    def _capture_query_id(self) -> None:
        with self._provider_lock:
            if self._query_id is not None:
                return
            provider: Callable[[], str | None] | None = self._query_id_provider
            if provider is None:
                return
            try:
                query_id: str | None = provider()
            except BaseException:
                return
            if not isinstance(query_id, str) or not query_id:
                return
            self._query_id = query_id
            try:
                self._on_submitted(query_id)
            except BaseException:
                pass

    def _has_query_id_provider(self) -> bool:
        with self._provider_lock:
            return self._query_id_provider is not None

    def _safe_heartbeat(self, *, elapsed_seconds: float) -> None:
        try:
            self._on_heartbeat(elapsed_seconds, self._query_id)
        except BaseException:
            pass
