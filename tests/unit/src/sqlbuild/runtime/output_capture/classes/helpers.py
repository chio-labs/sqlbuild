"""Output capture test doubles and factories."""

from __future__ import annotations

import threading
from collections.abc import Callable, Mapping
from datetime import UTC, datetime

from sqlbuild.runtime.output_capture.classes.dispatcher import OutputCaptureDispatcher
from sqlbuild.runtime.output_capture.models import CommandOutputRecord


class RecordingOutputExporter:
    """Thread-safe output exporter test double."""

    def __init__(self) -> None:
        self.records: list[CommandOutputRecord] = []
        self.called = threading.Event()

    def export_output(self, records: tuple[CommandOutputRecord, ...]) -> None:
        self.records.extend(records)
        self.called.set()


class BlockingOutputExporter(RecordingOutputExporter):
    """Exporter whose first batch remains in flight until released."""

    def __init__(self) -> None:
        super().__init__()
        self.release = threading.Event()

    def export_output(self, records: tuple[CommandOutputRecord, ...]) -> None:
        super().export_output(records)
        self.release.wait()


class FailingOutputExporter:
    """Exporter that always fails."""

    def __init__(self) -> None:
        self.called = threading.Event()

    def export_output(self, records: tuple[CommandOutputRecord, ...]) -> None:
        del records
        self.called.set()
        raise RuntimeError("destination unavailable")


class DiagnosingFailingOutputExporter(FailingOutputExporter):
    """Failing exporter that writes one destination diagnostic first."""

    def __init__(self, diagnostic: Callable[[], None]) -> None:
        super().__init__()
        self._diagnostic: Callable[[], None] = diagnostic

    def export_output(self, records: tuple[CommandOutputRecord, ...]) -> None:
        self._diagnostic()
        super().export_output(records)


def fixed_clock() -> datetime:
    """Return a stable UTC timestamp."""

    return datetime(2026, 9, 4, 12, tzinfo=UTC)


def make_dispatcher(
    *,
    exporter: object,
    queue_capacity: int = 32,
    batch_size: int = 32,
    max_record_bytes: int = 64,
    shutdown_timeout_seconds: float = 0.5,
    external_context: Mapping[str, object] | None = None,
    failure_callback: Callable[[BaseException], object] | None = None,
) -> OutputCaptureDispatcher:
    """Build a deterministic dispatcher for focused tests."""

    return OutputCaptureDispatcher(
        exporter=exporter,
        invocation_id="invocation-1",
        run_id="run-1",
        external_context=external_context,
        queue_capacity=queue_capacity,
        batch_size=batch_size,
        max_record_bytes=max_record_bytes,
        shutdown_timeout_seconds=shutdown_timeout_seconds,
        clock=fixed_clock,
        failure_callback=failure_callback,
    )
