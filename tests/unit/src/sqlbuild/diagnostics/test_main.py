"""Tests for diagnostics logging."""

from __future__ import annotations

import logging
import sys
import threading
from pathlib import Path

import pytest

from sqlbuild._native import TransientStatusReporter
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.diagnostics.main.configure import configure_diagnostics
from sqlbuild.diagnostics.main.diagnostics_context import diagnostics_context
from sqlbuild.diagnostics.main.log_sql import log_sql
from tests.unit.src.sqlbuild.diagnostics._test_types import (
    ConsoleProgressLineTestCase,
    DiagnosticsContextualSqlTestCase,
    DiagnosticsLogTestCase,
    SpinnerReuseTestCase,
    ThirdPartyConsoleTestCase,
)
from tests.unit.src.sqlbuild.diagnostics.helpers import (
    HostRecordingLogHandler,
    log_vendor_records,
    spinner_threads,
    spinner_threads_started_after,
    stopped_after_join,
)
from tests.unit.src.sqlbuild.presentation.classes.helpers import RecordingStream

_CLEAR_LINE: str = "\r\x1b[K"


@pytest.mark.parametrize(
    "test_case",
    [
        DiagnosticsLogTestCase(
            description="suppresses internal debug diagnostics without debug mode",
            debug=False,
            message="file-only diagnostic",
            expected_absent_console_fragments=("file-only diagnostic",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_diagnostics_without_debug_when_logging_then_internal_records_are_suppressed(
    test_case: DiagnosticsLogTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    del tmp_path
    with configure_diagnostics(debug=test_case.debug):
        logger: logging.Logger = logging.getLogger("sqlbuild.unit")
        logger.debug(test_case.message)
        adapter: DuckDbAdapter = DuckDbAdapter()
        connection: object = adapter.connect({"database": ":memory:"})
        adapter.execute(connection=connection, sql="SELECT 1")
        adapter.close(connection)

    console_error: str = capsys.readouterr().err

    absent_fragment: str
    for absent_fragment in test_case.expected_absent_console_fragments:
        assert absent_fragment not in console_error


@pytest.mark.parametrize(
    "test_case",
    (
        ThirdPartyConsoleTestCase(
            description="normal console hides INFO and shows WARNING as one line",
            debug=False,
            expected_console_lines=(
                "[warning] vendor.client token refresh failed",
                "[error] vendor.client orders service rejected the request",
            ),
            expected_absent=("connecting to the orders service", "retrying with fallback"),
            expected_traceback_count=1,
        ),
        ThirdPartyConsoleTestCase(
            description="debug console shows every record with tracebacks",
            debug=True,
            expected_console_lines=(
                "[info] vendor.client connecting to the orders service",
                "[warning] vendor.client token refresh failed",
                "retrying with fallback",
                "[error] vendor.client orders service rejected the request",
            ),
            expected_absent=(),
            expected_traceback_count=2,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_third_party_records_when_logging_then_console_follows_debug_policy(
    test_case: ThirdPartyConsoleTestCase,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with configure_diagnostics(debug=test_case.debug):
        log_vendor_records()

    console_error: str = capsys.readouterr().err

    assert all(line in console_error for line in test_case.expected_console_lines), console_error
    assert not any(fragment in console_error for fragment in test_case.expected_absent)
    assert console_error.count("Traceback (most recent call last):") == (
        test_case.expected_traceback_count
    )


@pytest.mark.parametrize(
    "test_case",
    (
        ConsoleProgressLineTestCase(
            description="warning clears the live status line and redraws it afterwards",
            message="Preparing clone plan...",
            expected_log_line="[warning] vendor.client token refresh failed\n",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_live_status_line_when_logging_then_line_is_cleared_before_record(
    test_case: ConsoleProgressLineTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SQLBUILD_NO_PROGRESS", raising=False)
    events: list[str] = []
    stream: RecordingStream = RecordingStream(events=events, tty=True)
    monkeypatch.setattr(sys, "stderr", stream)
    reporter: TransientStatusReporter = TransientStatusReporter(stream=stream, use_color=False)
    reporter.start(test_case.message)
    try:
        with configure_diagnostics(debug=False):
            logging.getLogger("vendor.client").warning("token refresh failed")
    finally:
        reporter.close()

    log_index: int = events.index(f"write:{test_case.expected_log_line}")
    assert any(
        event.startswith(f"write:{_CLEAR_LINE}") for event in events[log_index - 2 : log_index]
    ), events
    assert any(test_case.message in event for event in events[log_index + 1 :]), events


@pytest.mark.parametrize(
    "test_case",
    (
        SpinnerReuseTestCase(
            description="debug records around one status line reuse its spinner thread",
            record_count=200,
            expected_spinner_threads=1,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_many_records_during_status_line_when_logging_then_one_spinner_thread_runs(
    test_case: SpinnerReuseTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SQLBUILD_NO_PROGRESS", raising=False)
    stream: RecordingStream = RecordingStream(events=[], tty=True)
    monkeypatch.setattr(sys, "stderr", stream)
    reporter: TransientStatusReporter = TransientStatusReporter(stream=stream, use_color=False)
    earlier: list[threading.Thread] = spinner_threads()
    seen: list[threading.Thread] = []
    reporter.start("Preparing clone plan...")
    try:
        with configure_diagnostics(debug=True):
            for index in range(test_case.record_count):
                logging.getLogger("vendor.client").warning("retrying request %d", index)
                seen.extend(spinner_threads_started_after(earlier))
    finally:
        reporter.close()

    started: list[threading.Thread] = list({id(thread): thread for thread in seen}.values())
    assert len(started) == test_case.expected_spinner_threads
    assert stopped_after_join(started, timeout_seconds=5.0)
    assert stream.getvalue().count("retrying request") == test_case.record_count


@pytest.mark.parametrize(
    "test_case",
    [
        DiagnosticsLogTestCase(
            description="mirrors debug diagnostics to stderr",
            debug=True,
            message="console diagnostic",
            expected_console_fragments=("[debug] unit console diagnostic",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_diagnostics_with_debug_when_logging_then_mirrors_to_stderr(
    test_case: DiagnosticsLogTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    del tmp_path
    with configure_diagnostics(debug=test_case.debug):
        logger: logging.Logger = logging.getLogger("sqlbuild.unit")
        logger.debug(test_case.message)

    console_error: str = capsys.readouterr().err

    expected_fragment: str
    for expected_fragment in test_case.expected_console_fragments:
        assert expected_fragment in console_error


@pytest.mark.parametrize(
    "test_case",
    [
        DiagnosticsLogTestCase(
            description="SQL text is never written to the console",
            debug=True,
            message="",
            expected_console_fragments=("[debug] adapter.duckdb SQL diagnostic omitted",),
            expected_absent_console_fragments=(
                "\\n  1 AS id",
                "CREATE OR REPLACE VIEW main.debug_view AS SELECT",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_multiline_sql_when_debug_logging_then_formats_readable_outputs(
    test_case: DiagnosticsLogTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    del tmp_path
    with configure_diagnostics(debug=test_case.debug):
        adapter: DuckDbAdapter = DuckDbAdapter()
        connection: object = adapter.connect({"database": ":memory:"})
        adapter.execute(
            connection=connection,
            sql="CREATE OR REPLACE VIEW main.debug_view AS SELECT\n  1 AS id",
        )
        adapter.close(connection)

    console_error: str = capsys.readouterr().err

    expected_fragment: str
    for expected_fragment in test_case.expected_console_fragments:
        assert expected_fragment in console_error
    absent_fragment: str
    for absent_fragment in test_case.expected_absent_console_fragments:
        assert absent_fragment not in console_error


@pytest.mark.parametrize(
    "test_case",
    [
        DiagnosticsContextualSqlTestCase(
            description="renders inline contextual transaction SQL",
            debug=True,
            sql="BEGIN",
            context={
                "sqlbuild_subject": "model",
                "sqlbuild_name": "daily_revenue",
                "sqlbuild_phase": "promote",
                "sqlbuild_action_name": "begin_txn",
            },
            expected_console_fragment=(
                "[debug] model daily_revenue phase=promote action=begin_txn SQL diagnostic omitted"
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_contextual_transaction_sql_when_debug_logging_then_console_renders_inline(
    test_case: DiagnosticsContextualSqlTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    del tmp_path
    with configure_diagnostics(debug=test_case.debug):
        adapter: DuckDbAdapter = DuckDbAdapter()
        connection: object = adapter.connect({"database": ":memory:"})

        with diagnostics_context(**test_case.context):
            adapter.execute(connection=connection, sql=test_case.sql)

        adapter.close(connection)

    console_error: str = capsys.readouterr().err

    assert test_case.expected_console_fragment in console_error
    assert test_case.sql not in console_error


@pytest.mark.parametrize(
    "test_case",
    [
        DiagnosticsLogTestCase(
            description="existing legacy diagnostics remain untouched",
            debug=False,
            message="new diagnostic",
            expected_fragments=("existing diagnostic",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_existing_legacy_file_when_routing_then_file_is_untouched(
    test_case: DiagnosticsLogTestCase, tmp_path: Path
) -> None:
    target_dir: Path = tmp_path / "target"
    target_dir.mkdir()
    legacy_path: Path = target_dir / "sqlbuild.log"
    legacy_path.write_text("existing diagnostic\n", encoding="utf-8")

    with configure_diagnostics(debug=test_case.debug):
        logging.getLogger("sqlbuild.unit").debug(test_case.message)

    log_text: str = legacy_path.read_text(encoding="utf-8")
    for expected_fragment in test_case.expected_fragments:
        assert expected_fragment in log_text
    assert test_case.message not in log_text


@pytest.mark.parametrize(
    "test_case",
    [
        DiagnosticsLogTestCase(
            description="nested exceptional routes restore every prior logger attribute",
            debug=False,
            message="nested failure",
            expected_fragments=(),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_nested_routing_exception_when_exiting_then_exact_logging_state_is_restored(
    test_case: DiagnosticsLogTestCase, tmp_path: Path
) -> None:
    root_logger: logging.Logger = logging.getLogger()
    internal_logger: logging.Logger = logging.getLogger("sqlbuild")
    root_state: tuple[int, tuple[logging.Handler, ...], bool] = (
        root_logger.level,
        tuple(root_logger.handlers),
        root_logger.propagate,
    )
    internal_state: tuple[int, tuple[logging.Handler, ...], bool] = (
        internal_logger.level,
        tuple(internal_logger.handlers),
        internal_logger.propagate,
    )

    del tmp_path
    with configure_diagnostics(debug=test_case.debug):
        outer_root_state: tuple[int, tuple[logging.Handler, ...], bool] = (
            root_logger.level,
            tuple(root_logger.handlers),
            root_logger.propagate,
        )
        with pytest.raises(RuntimeError, match=test_case.message):
            with configure_diagnostics(debug=True):
                raise RuntimeError(test_case.message)
        assert (root_logger.level, tuple(root_logger.handlers), root_logger.propagate) == (
            outer_root_state
        )

    assert (root_logger.level, tuple(root_logger.handlers), root_logger.propagate) == root_state
    assert (
        internal_logger.level,
        tuple(internal_logger.handlers),
        internal_logger.propagate,
    ) == internal_state
    assert test_case.expected_fragments == ()


@pytest.mark.parametrize(
    "test_case",
    [
        DiagnosticsLogTestCase(
            description="host handlers survive nested routes and never receive full SQL",
            debug=True,
            message="host-visible-safe-record",
            expected_fragments=("outer-before", "outer-after"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_host_handlers_and_nested_routes_when_logging_then_only_owned_handlers_suspend(
    test_case: DiagnosticsLogTestCase, tmp_path: Path
) -> None:
    root_logger: logging.Logger = logging.getLogger()
    internal_logger: logging.Logger = logging.getLogger("sqlbuild")
    root_host: HostRecordingLogHandler = HostRecordingLogHandler()
    internal_host: HostRecordingLogHandler = HostRecordingLogHandler()
    root_logger.addHandler(root_host)
    internal_logger.addHandler(internal_host)
    outer_sql: str = "SELECT 'outer-private-value'"
    inner_sql: str = "SELECT 'inner-private-value'"
    try:
        with configure_diagnostics(debug=test_case.debug):
            logging.getLogger("sqlbuild.host").debug("outer-before")
            log_sql(logger=logging.getLogger("sqlbuild.host"), sql=outer_sql)
            with configure_diagnostics(debug=False):
                logging.getLogger("sqlbuild.host").debug(test_case.message)
                log_sql(logger=logging.getLogger("sqlbuild.host"), sql=inner_sql)
            logging.getLogger("sqlbuild.host").debug("outer-after")
    finally:
        root_logger.removeHandler(root_host)
        internal_logger.removeHandler(internal_host)

    assert not (tmp_path / "outer" / "sqlbuild.log").exists()
    assert not (tmp_path / "inner" / "sqlbuild.log").exists()
    host_text: str = "\n".join(record.getMessage() for record in root_host.records)
    host_fields: str = repr([record.__dict__ for record in root_host.records])
    for expected_fragment in test_case.expected_fragments:
        assert host_text.count(expected_fragment) == 1
    assert test_case.message in host_text
    assert outer_sql not in host_text
    assert inner_sql not in host_text
    assert outer_sql not in host_fields
    assert inner_sql not in host_fields
    assert root_host.was_closed is False
    assert internal_host.was_closed is False
