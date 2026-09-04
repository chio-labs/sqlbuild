"""Behavior tests for asynchronous command output capture."""

from __future__ import annotations

import io
import sys
import threading
import time

import pytest

from sqlbuild.runtime.output_capture.classes.dispatcher import OutputCaptureDispatcher
from sqlbuild.runtime.output_capture.classes.text_tee import TextOutputTee
from sqlbuild.runtime.output_capture.models import CommandOutputCaptureSummary
from sqlbuild.runtime.output_capture.types import CommandOutputStream
from tests.unit.src.sqlbuild.runtime.output_capture.classes._test_types import (
    ChunkingTestCase,
    OutputCaptureTestCase,
)
from tests.unit.src.sqlbuild.runtime.output_capture.classes.helpers import (
    BlockingOutputExporter,
    DiagnosingFailingOutputExporter,
    FailingOutputExporter,
    RecordingOutputExporter,
    make_dispatcher,
)


@pytest.mark.parametrize(
    "test_case",
    (OutputCaptureTestCase(description="ansi_passthrough", expected_success=True),),
    ids=lambda case: case.description,
)
def test_given_ansi_terminal_text_when_captured_then_passthrough_is_byte_for_byte_unchanged(
    test_case: OutputCaptureTestCase,
) -> None:
    assert test_case.expected_success is True
    sink: io.StringIO = io.StringIO()
    exporter: RecordingOutputExporter = RecordingOutputExporter()
    dispatcher: OutputCaptureDispatcher = make_dispatcher(exporter=exporter)
    tee: TextOutputTee = TextOutputTee(
        sink=sink, dispatcher=dispatcher, stream=CommandOutputStream.STDOUT
    )

    written: int = tee.write("\x1b[31mfailed\x1b[0m\n")
    summary: CommandOutputCaptureSummary = dispatcher.close()

    assert written == 16
    assert sink.getvalue() == "\x1b[31mfailed\x1b[0m\n"
    assert tuple(record.message for record in exporter.records) == ("failed\n",)
    assert summary.flush_complete is True


@pytest.mark.parametrize(
    "test_case",
    (OutputCaptureTestCase(description="partial_writes", expected_success=True),),
    ids=lambda case: case.description,
)
def test_given_interleaved_partial_writes_when_closed_then_complete_lines_have_global_sequence(
    test_case: OutputCaptureTestCase,
) -> None:
    assert test_case.expected_success is True
    exporter: RecordingOutputExporter = RecordingOutputExporter()
    dispatcher: OutputCaptureDispatcher = make_dispatcher(exporter=exporter, batch_size=1)

    dispatcher.append(stream=CommandOutputStream.STDOUT, text="out")
    dispatcher.append(stream=CommandOutputStream.STDERR, text="error\n")
    dispatcher.append(stream=CommandOutputStream.STDOUT, text="put\n")
    summary: CommandOutputCaptureSummary = dispatcher.close()

    assert tuple(record.sequence for record in exporter.records) == (0, 1)
    assert tuple(record.stream for record in exporter.records) == (
        CommandOutputStream.STDERR,
        CommandOutputStream.STDOUT,
    )
    assert tuple(record.message for record in exporter.records) == ("error\n", "output\n")
    assert summary.delivered == 2


@pytest.mark.parametrize(
    "test_case",
    (
        ChunkingTestCase("ascii_sql", "SELECT 123456789\n", 8, ("SELECT 1", "23456789", "\n")),
        ChunkingTestCase("unicode_sql", "ééé\n", 4, ("éé", "é\n")),
    ),
    ids=lambda case: case.description,
)
def test_given_oversized_line_when_captured_then_chunks_are_deterministic(
    test_case: ChunkingTestCase,
) -> None:
    exporter: RecordingOutputExporter = RecordingOutputExporter()
    dispatcher: OutputCaptureDispatcher = make_dispatcher(
        exporter=exporter, max_record_bytes=test_case.max_record_bytes
    )

    dispatcher.append(stream=CommandOutputStream.STDOUT, text=test_case.text)
    summary: CommandOutputCaptureSummary = dispatcher.close()

    assert tuple(record.message for record in exporter.records) == test_case.expected_messages
    assert tuple(record.chunk_index for record in exporter.records) == tuple(
        range(len(test_case.expected_messages))
    )
    assert {record.chunk_count for record in exporter.records} == {len(test_case.expected_messages)}
    assert summary.flush_complete is True


@pytest.mark.parametrize(
    "test_case",
    (OutputCaptureTestCase(description="priority_overflow", expected_success=True),),
    ids=lambda case: case.description,
)
def test_given_full_queue_when_terminal_summary_arrives_then_bulk_is_dropped_and_counted(
    test_case: OutputCaptureTestCase,
) -> None:
    assert test_case.expected_success is True
    exporter: BlockingOutputExporter = BlockingOutputExporter()
    dispatcher: OutputCaptureDispatcher = make_dispatcher(
        exporter=exporter,
        queue_capacity=2,
        batch_size=1,
    )
    dispatcher.append(stream=CommandOutputStream.STDOUT, text="first\n")
    assert exporter.called.wait(timeout=1.0)

    dispatcher.append(stream=CommandOutputStream.STDOUT, text="second\n")
    dispatcher.append(stream=CommandOutputStream.STDOUT, text="third\n")
    dispatcher.append(stream=CommandOutputStream.STDOUT, text="fourth\n")
    release_timer: threading.Timer = threading.Timer(0.02, exporter.release.set)
    release_timer.start()
    summary: CommandOutputCaptureSummary = dispatcher.close()

    assert summary.dropped == 2
    assert summary.flush_complete is True
    assert tuple(record.record_type for record in exporter.records) == (
        "command_output",
        "command_output",
        "command_output_loss",
    )
    assert tuple(record.dropped_records for record in exporter.records) == (0, 0, 2)


@pytest.mark.parametrize(
    "test_case",
    (OutputCaptureTestCase(description="bounded_shutdown", expected_success=True),),
    ids=lambda case: case.description,
)
def test_given_slow_exporter_when_shutdown_then_return_is_bounded_and_run_is_unfailed(
    test_case: OutputCaptureTestCase,
) -> None:
    assert test_case.expected_success is True
    exporter: BlockingOutputExporter = BlockingOutputExporter()
    dispatcher: OutputCaptureDispatcher = make_dispatcher(
        exporter=exporter, shutdown_timeout_seconds=0.01
    )
    dispatcher.append(stream=CommandOutputStream.STDOUT, text="line\n")
    assert exporter.called.wait(timeout=1.0)

    started: float = time.monotonic()
    summary: CommandOutputCaptureSummary = dispatcher.close()
    elapsed: float = time.monotonic() - started
    exporter.release.set()

    assert elapsed < 0.2
    assert summary.flush_complete is False
    assert summary.failed == 0


@pytest.mark.parametrize(
    "test_case",
    (OutputCaptureTestCase(description="export_failure", expected_success=True),),
    ids=lambda case: case.description,
)
def test_given_exporter_failure_when_delivering_then_failure_is_isolated_and_accounted(
    test_case: OutputCaptureTestCase,
) -> None:
    assert test_case.expected_success is True
    failures: list[str] = []
    exporter: FailingOutputExporter = FailingOutputExporter()
    dispatcher: OutputCaptureDispatcher = make_dispatcher(
        exporter=exporter, failure_callback=lambda error: failures.append(type(error).__name__)
    )

    dispatcher.append(stream=CommandOutputStream.STDERR, text="problem\n")
    summary: CommandOutputCaptureSummary = dispatcher.close()

    assert failures == ["RuntimeError"]
    assert summary.failed == 1
    assert summary.delivered == 0
    assert summary.flush_complete is True


@pytest.mark.parametrize(
    "test_case",
    (OutputCaptureTestCase(description="opaque_context", expected_success=True),),
    ids=lambda case: case.description,
)
def test_given_external_context_when_exporting_then_it_is_attached_opaquely(
    test_case: OutputCaptureTestCase,
) -> None:
    assert test_case.expected_success is True
    exporter: RecordingOutputExporter = RecordingOutputExporter()
    context: dict[str, object] = {"orchestrator": {"opaque": 7}}
    dispatcher: OutputCaptureDispatcher = make_dispatcher(
        exporter=exporter, external_context=context
    )

    dispatcher.append(stream=CommandOutputStream.STDOUT, text="ok\n")
    summary: CommandOutputCaptureSummary = dispatcher.close()

    assert exporter.records[0].external_context == context
    assert exporter.records[0].invocation_id == "invocation-1"
    assert exporter.records[0].run_id == "run-1"
    assert summary.delivered == 1


@pytest.mark.parametrize(
    "test_case",
    (OutputCaptureTestCase(description="absent_context", expected_success=True),),
    ids=lambda case: case.description,
)
def test_given_absent_external_context_when_exporting_then_empty_mapping_is_attached(
    test_case: OutputCaptureTestCase,
) -> None:
    assert test_case.expected_success is True
    exporter: RecordingOutputExporter = RecordingOutputExporter()
    dispatcher: OutputCaptureDispatcher = make_dispatcher(exporter=exporter)

    dispatcher.append(stream=CommandOutputStream.STDOUT, text="ok\n")
    summary: CommandOutputCaptureSummary = dispatcher.close()

    assert exporter.records[0].external_context == {}
    assert summary.delivered == 1


@pytest.mark.parametrize(
    "test_case",
    (OutputCaptureTestCase(description="diagnostic_recursion", expected_success=True),),
    ids=lambda case: case.description,
)
def test_given_exporter_diagnostic_when_exporting_then_diagnostic_is_not_recaptured(
    test_case: OutputCaptureTestCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert test_case.expected_success is True
    sink: io.StringIO = io.StringIO()
    exporter: DiagnosingFailingOutputExporter = DiagnosingFailingOutputExporter(
        diagnostic=lambda: print("export diagnostic", file=sys.stderr)
    )
    dispatcher: OutputCaptureDispatcher = make_dispatcher(exporter=exporter)
    tee: TextOutputTee = TextOutputTee(
        sink=sink, dispatcher=dispatcher, stream=CommandOutputStream.STDERR
    )
    monkeypatch.setattr(sys, "stderr", tee)

    tee.write("command output\n")
    summary: CommandOutputCaptureSummary = dispatcher.close()

    assert sink.getvalue() == "command output\nexport diagnostic\n"
    assert summary.accepted == 1
    assert summary.failed == 1


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
