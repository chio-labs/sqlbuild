"""Bounded asynchronous delivery of captured output batches."""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import cast

from sqlbuild.runtime.output_capture._helpers.json import freeze_command_output_json
from sqlbuild.runtime.output_capture._helpers.text import chunk_text, strip_ansi
from sqlbuild.runtime.output_capture.constants import (
    COMMAND_OUTPUT_LOSS_RECORD_TYPE,
    DEFAULT_OUTPUT_BATCH_SIZE,
    DEFAULT_OUTPUT_FLUSH_INTERVAL_SECONDS,
    DEFAULT_OUTPUT_MAX_RECORD_BYTES,
    DEFAULT_OUTPUT_QUEUE_CAPACITY,
    DEFAULT_OUTPUT_SHUTDOWN_TIMEOUT_SECONDS,
    MIN_OUTPUT_RECORD_BYTES,
)
from sqlbuild.runtime.output_capture.exceptions import OutputCaptureInputError
from sqlbuild.runtime.output_capture.models import (
    CommandOutputCaptureSummary,
    CommandOutputRecord,
)
from sqlbuild.runtime.output_capture.types import (
    CommandOutputBatchExporter,
    CommandOutputStream,
    OutputRecordPriority,
)


class OutputCaptureDispatcher:
    """Turn stream fragments into bounded text chunks and export them off execution threads."""

    def __init__(
        self,
        *,
        exporter: object,
        invocation_id: str,
        run_id: str | None = None,
        external_context: Mapping[str, object] | None = None,
        queue_capacity: int = DEFAULT_OUTPUT_QUEUE_CAPACITY,
        batch_size: int = DEFAULT_OUTPUT_BATCH_SIZE,
        max_record_bytes: int = DEFAULT_OUTPUT_MAX_RECORD_BYTES,
        shutdown_timeout_seconds: float = DEFAULT_OUTPUT_SHUTDOWN_TIMEOUT_SECONDS,
        clock: Callable[[], datetime] | None = None,
        failure_callback: Callable[[BaseException], object] | None = None,
    ) -> None:
        if queue_capacity < 1 or batch_size < 1:
            raise OutputCaptureInputError(
                "output capture queue capacity and batch size must be positive"
            )
        if max_record_bytes < MIN_OUTPUT_RECORD_BYTES or shutdown_timeout_seconds < 0:
            raise OutputCaptureInputError("output capture limits are invalid")
        self._exporter: object = exporter
        self._invocation_id: str = invocation_id
        self._run_id: str | None = run_id
        frozen_context: object = freeze_command_output_json(
            value=dict(external_context or {}),
            path="external_context",
        )
        if not isinstance(frozen_context, Mapping):
            raise OutputCaptureInputError("output capture external_context must be a mapping")
        self._context: Mapping[str, object] = cast(Mapping[str, object], frozen_context)
        self._capacity: int = queue_capacity
        self._batch_size: int = batch_size
        self._max_record_bytes: int = max_record_bytes
        self._flush_interval_seconds: float = DEFAULT_OUTPUT_FLUSH_INTERVAL_SECONDS
        self._shutdown_timeout_seconds: float = shutdown_timeout_seconds
        self._clock: Callable[[], datetime] = clock or (lambda: datetime.now(UTC))
        self._failure_callback: Callable[[BaseException], object] | None = failure_callback
        self._queue: deque[CommandOutputRecord] = deque()
        self._buffer_stream: CommandOutputStream | None = None
        self._buffer_parts: list[str] = []
        self._buffer_bytes: int = 0
        self._buffer_started_at: float | None = None
        self._partials: dict[CommandOutputStream, str] = {
            CommandOutputStream.STDOUT: "",
            CommandOutputStream.STDERR: "",
        }
        self._condition = threading.Condition()
        self._sequence: int = 0
        self._accepted: int = 0
        self._delivered: int = 0
        self._failed: int = 0
        self._dropped: int = 0
        self._accepting: bool = True
        self._stopping: bool = False
        self._force_stop: bool = False
        self._worker_finished: bool = False
        self._suppressed_threads: set[int] = set()
        self._thread = threading.Thread(
            target=self._run, name="sqlbuild-output-exporter", daemon=True
        )
        self._thread.start()

    def append(self, *, stream: CommandOutputStream, text: str) -> None:
        """Accept one stream fragment without waiting for destination work."""

        if not text or threading.get_ident() in self._suppressed_threads:
            return
        with self._condition:
            if not self._accepting:
                return
            combined: str = self._partials[stream] + text
            lines: list[str] = combined.splitlines(keepends=True)
            trailing: str = ""
            if lines and not lines[-1].endswith(("\n", "\r")):
                trailing = lines.pop()
            self._partials[stream] = trailing
            for line in lines:
                self._buffer_text_fragment(
                    stream=stream, text=line, immediate_priority=OutputRecordPriority.BULK
                )
            self._condition.notify()

    def close(self) -> CommandOutputCaptureSummary:
        """Flush partial records until a fixed deadline and return without indefinite waits."""

        with self._condition:
            if self._accepting:
                for stream, partial in self._partials.items():
                    if partial:
                        self._buffer_text_fragment(
                            stream=stream,
                            text=partial,
                            immediate_priority=OutputRecordPriority.TERMINAL,
                        )
                        self._flush_buffer(priority=OutputRecordPriority.TERMINAL)
                self._flush_buffer(priority=OutputRecordPriority.TERMINAL)
                self._partials = {
                    CommandOutputStream.STDOUT: "",
                    CommandOutputStream.STDERR: "",
                }
                self._accepting = False
                if self._dropped:
                    self._enqueue_loss_summary()
                self._stopping = True
                self._condition.notify_all()
        deadline: float = time.monotonic() + self._shutdown_timeout_seconds
        self._thread.join(timeout=max(0.0, deadline - time.monotonic()))
        with self._condition:
            if self._thread.is_alive():
                self._force_stop = True
                self._dropped += len(self._queue)
                self._queue.clear()
                self._condition.notify_all()
            return CommandOutputCaptureSummary(
                accepted=self._accepted,
                delivered=self._delivered,
                failed=self._failed,
                dropped=self._dropped,
                queue_depth=len(self._queue),
                queue_capacity=self._capacity,
                flush_complete=self._worker_finished and not self._queue,
            )

    def _buffer_text_fragment(
        self,
        *,
        stream: CommandOutputStream,
        text: str,
        immediate_priority: OutputRecordPriority,
    ) -> None:
        plain: str = strip_ansi(text)
        chunks: tuple[str, ...] = chunk_text(text=plain, max_bytes=self._max_record_bytes)
        if len(chunks) > 1:
            self._flush_buffer(priority=OutputRecordPriority.BULK)
            self._enqueue_chunks(stream=stream, chunks=chunks, priority=immediate_priority)
            return
        chunk: str = chunks[0]
        if self._buffer_stream is not None and self._buffer_stream is not stream:
            self._flush_buffer(priority=OutputRecordPriority.BULK)
        chunk_bytes: int = len(chunk.encode("utf-8"))
        if self._buffer_parts and self._buffer_bytes + chunk_bytes > self._max_record_bytes:
            self._flush_buffer(priority=OutputRecordPriority.BULK)
        if not self._buffer_parts:
            self._buffer_stream = stream
            self._buffer_started_at = time.monotonic()
        self._buffer_parts.append(chunk)
        self._buffer_bytes += chunk_bytes

    def _flush_buffer(self, *, priority: OutputRecordPriority) -> None:
        if not self._buffer_parts or self._buffer_stream is None:
            return
        stream: CommandOutputStream = self._buffer_stream
        text: str = "".join(self._buffer_parts)
        self._buffer_stream = None
        self._buffer_parts = []
        self._buffer_bytes = 0
        self._buffer_started_at = None
        self._enqueue_chunks(stream=stream, chunks=(text,), priority=priority)

    def _enqueue_chunks(
        self,
        *,
        stream: CommandOutputStream,
        chunks: tuple[str, ...],
        priority: OutputRecordPriority,
    ) -> None:
        for index, chunk in enumerate(chunks):
            record: CommandOutputRecord = CommandOutputRecord(
                invocation_id=self._invocation_id,
                run_id=self._run_id,
                sequence=self._next_sequence(),
                occurred_at=self._clock(),
                stream=stream,
                message=chunk,
                external_context=self._context,
                chunk_index=index,
                chunk_count=len(chunks),
                priority=priority,
            )
            self._put(record)

    def _put(self, record: CommandOutputRecord) -> None:
        self._accepted += 1
        if len(self._queue) < self._capacity:
            self._queue.append(record)
            return
        if record.priority is OutputRecordPriority.TERMINAL:
            for queued in self._queue:
                if queued.priority is OutputRecordPriority.BULK:
                    self._queue.remove(queued)
                    self._dropped += 1
                    self._queue.append(record)
                    return
        self._dropped += 1

    def _enqueue_loss_summary(self) -> None:
        summary_displaces_bulk: bool = len(self._queue) >= self._capacity and any(
            queued.priority is OutputRecordPriority.BULK for queued in self._queue
        )
        dropped_before_summary: int = self._dropped + int(summary_displaces_bulk)
        record: CommandOutputRecord = CommandOutputRecord(
            invocation_id=self._invocation_id,
            run_id=self._run_id,
            sequence=self._next_sequence(),
            occurred_at=self._clock(),
            stream=CommandOutputStream.STDERR,
            message=f"SQLBuild output export dropped {dropped_before_summary} record(s)",
            external_context=self._context,
            priority=OutputRecordPriority.TERMINAL,
            record_type=COMMAND_OUTPUT_LOSS_RECORD_TYPE,
            dropped_records=dropped_before_summary,
        )
        self._put(record)

    def _next_sequence(self) -> int:
        sequence: int = self._sequence
        self._sequence += 1
        return sequence

    def _run(self) -> None:
        try:
            while True:
                with self._condition:
                    while not self._queue and not self._stopping:
                        if self._buffer_started_at is None:
                            self._condition.wait()
                            continue
                        remaining: float = (
                            self._buffer_started_at
                            + self._flush_interval_seconds
                            - time.monotonic()
                        )
                        if remaining > 0:
                            self._condition.wait(timeout=remaining)
                            continue
                        self._flush_buffer(priority=OutputRecordPriority.BULK)
                    if self._force_stop or (not self._queue and self._stopping):
                        return
                    batch: tuple[CommandOutputRecord, ...] = tuple(
                        self._queue.popleft()
                        for _ in range(min(self._batch_size, len(self._queue)))
                    )
                self._export(batch)
        finally:
            with self._condition:
                self._worker_finished = True
                self._condition.notify_all()

    def _export(self, batch: tuple[CommandOutputRecord, ...]) -> None:
        thread_id: int = threading.get_ident()
        self._suppressed_threads.add(thread_id)
        try:
            exporter: CommandOutputBatchExporter = cast(CommandOutputBatchExporter, self._exporter)
            exporter.export_output(batch)
        except BaseException as error:
            with self._condition:
                self._failed += len(batch)
            if self._failure_callback is not None:
                try:
                    self._failure_callback(error)
                except BaseException:
                    pass
        else:
            with self._condition:
                self._delivered += len(batch)
        finally:
            self._suppressed_threads.discard(thread_id)
