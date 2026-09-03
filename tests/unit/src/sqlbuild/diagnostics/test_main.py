"""Tests for diagnostics logging."""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.diagnostics.classes.safe_diagnostic_file_handler import SafeDiagnosticFileHandler
from sqlbuild.diagnostics.main.configure import configure_diagnostics
from sqlbuild.diagnostics.main.diagnostics_context import diagnostics_context
from sqlbuild.diagnostics.main.log_sql import log_sql
from tests.unit.src.sqlbuild.diagnostics._test_types import (
    DiagnosticsContextualSqlTestCase,
    DiagnosticsLogTestCase,
)
from tests.unit.src.sqlbuild.diagnostics.helpers import HostRecordingLogHandler


@pytest.mark.parametrize(
    "test_case",
    [
        DiagnosticsLogTestCase(
            description="writes redacted debug diagnostics to append-only file",
            debug=False,
            message="file-only diagnostic",
            expected_file_fragments=(
                "DEBUG unit file-only diagnostic",
                "DEBUG adapter.duckdb SQL diagnostic omitted",
            ),
            expected_absent_file_fragments=("SELECT 1",),
            expected_absent_console_fragments=("file-only diagnostic",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_diagnostics_without_debug_when_logging_then_writes_file_only(
    test_case: DiagnosticsLogTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    target_dir: Path = tmp_path / "target"
    with configure_diagnostics(target_dir=target_dir, debug=test_case.debug):
        logger: logging.Logger = logging.getLogger("sqlbuild.unit")
        logger.debug(test_case.message)
        adapter: DuckDbAdapter = DuckDbAdapter()
        connection: object = adapter.connect({"database": ":memory:"})
        adapter.execute(connection=connection, sql="SELECT 1")
        adapter.close(connection)

    log_text: str = (target_dir / "sqlbuild.log").read_text(encoding="utf-8")
    console_error: str = capsys.readouterr().err

    expected_fragment: str
    for expected_fragment in test_case.expected_file_fragments:
        assert expected_fragment in log_text
    for absent_fragment in test_case.expected_absent_file_fragments:
        assert absent_fragment not in log_text
    absent_fragment: str
    for absent_fragment in test_case.expected_absent_console_fragments:
        assert absent_fragment not in console_error


@pytest.mark.parametrize(
    "test_case",
    [
        DiagnosticsLogTestCase(
            description="mirrors debug diagnostics to stderr",
            debug=True,
            message="console diagnostic",
            expected_file_fragments=("DEBUG unit console diagnostic",),
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
    target_dir: Path = tmp_path / "target"
    with configure_diagnostics(target_dir=target_dir, debug=test_case.debug):
        logger: logging.Logger = logging.getLogger("sqlbuild.unit")
        logger.debug(test_case.message)

    log_text: str = (target_dir / "sqlbuild.log").read_text(encoding="utf-8")
    console_error: str = capsys.readouterr().err

    expected_fragment: str
    for expected_fragment in test_case.expected_file_fragments:
        assert expected_fragment in log_text
    for expected_fragment in test_case.expected_console_fragments:
        assert expected_fragment in console_error


@pytest.mark.parametrize(
    "test_case",
    [
        DiagnosticsLogTestCase(
            description="explicit SQL retention is file-only and never console",
            debug=True,
            message="",
            expected_file_fragments=(
                "DEBUG adapter.duckdb SQL diagnostic omitted",
                "CREATE OR REPLACE VIEW main.debug_view AS SELECT\n  1 AS id",
            ),
            expected_console_fragments=("[debug] adapter.duckdb SQL diagnostic omitted",),
            expected_absent_file_fragments=("\\n  1 AS id",),
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
    target_dir: Path = tmp_path / "target"
    with configure_diagnostics(target_dir=target_dir, debug=test_case.debug, include_sql_text=True):
        adapter: DuckDbAdapter = DuckDbAdapter()
        connection: object = adapter.connect({"database": ":memory:"})
        adapter.execute(
            connection=connection,
            sql="CREATE OR REPLACE VIEW main.debug_view AS SELECT\n  1 AS id",
        )
        adapter.close(connection)

    log_text: str = (target_dir / "sqlbuild.log").read_text(encoding="utf-8")
    console_error: str = capsys.readouterr().err

    expected_fragment: str
    for expected_fragment in test_case.expected_file_fragments:
        assert expected_fragment in log_text
    for expected_fragment in test_case.expected_console_fragments:
        assert expected_fragment in console_error
    absent_fragment: str
    for absent_fragment in test_case.expected_absent_file_fragments:
        assert absent_fragment not in log_text
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
    target_dir: Path = tmp_path / "target"
    with configure_diagnostics(target_dir=target_dir, debug=test_case.debug):
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
            description="existing legacy diagnostics remain and new records append",
            debug=False,
            message="new diagnostic",
            expected_file_fragments=("existing diagnostic", "new diagnostic"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_existing_legacy_file_when_routing_then_new_diagnostics_append(
    test_case: DiagnosticsLogTestCase, tmp_path: Path
) -> None:
    target_dir: Path = tmp_path / "target"
    target_dir.mkdir()
    legacy_path: Path = target_dir / "sqlbuild.log"
    legacy_path.write_text("existing diagnostic\n", encoding="utf-8")

    with configure_diagnostics(target_dir=target_dir, debug=test_case.debug):
        logging.getLogger("sqlbuild.unit").debug(test_case.message)

    log_text: str = legacy_path.read_text(encoding="utf-8")
    for expected_fragment in test_case.expected_file_fragments:
        assert expected_fragment in log_text


@pytest.mark.parametrize(
    "test_case",
    [
        DiagnosticsLogTestCase(
            description="nested exceptional routes restore every prior logger attribute",
            debug=False,
            message="nested failure",
            expected_file_fragments=(),
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

    with configure_diagnostics(target_dir=tmp_path / "outer", debug=test_case.debug):
        outer_root_state: tuple[int, tuple[logging.Handler, ...], bool] = (
            root_logger.level,
            tuple(root_logger.handlers),
            root_logger.propagate,
        )
        with pytest.raises(RuntimeError, match=test_case.message):
            with configure_diagnostics(target_dir=tmp_path / "inner", debug=True):
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
    assert test_case.expected_file_fragments == ()


@pytest.mark.parametrize(
    "test_case",
    [
        DiagnosticsLogTestCase(
            description="host handlers survive nested routes and never receive full SQL",
            debug=True,
            message="host-visible-safe-record",
            expected_file_fragments=("outer-before", "outer-after"),
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
        with configure_diagnostics(
            target_dir=tmp_path / "outer", debug=test_case.debug, include_sql_text=True
        ):
            logging.getLogger("sqlbuild.host").debug("outer-before")
            log_sql(logger=logging.getLogger("sqlbuild.host"), sql=outer_sql)
            with configure_diagnostics(
                target_dir=tmp_path / "inner", debug=False, include_sql_text=True
            ):
                logging.getLogger("sqlbuild.host").debug(test_case.message)
                log_sql(logger=logging.getLogger("sqlbuild.host"), sql=inner_sql)
            logging.getLogger("sqlbuild.host").debug("outer-after")
    finally:
        root_logger.removeHandler(root_host)
        internal_logger.removeHandler(internal_host)

    outer_text: str = (tmp_path / "outer" / "sqlbuild.log").read_text(encoding="utf-8")
    inner_text: str = (tmp_path / "inner" / "sqlbuild.log").read_text(encoding="utf-8")
    host_text: str = "\n".join(record.getMessage() for record in root_host.records)
    host_fields: str = repr([record.__dict__ for record in root_host.records])
    for expected_fragment in test_case.expected_file_fragments:
        assert outer_text.count(expected_fragment) == 1
    assert inner_text.count(test_case.message) == 1
    assert test_case.message in host_text
    assert outer_sql not in host_text
    assert inner_sql not in host_text
    assert outer_sql not in host_fields
    assert inner_sql not in host_fields
    assert outer_text.count(outer_sql) == 1
    assert inner_text.count(inner_sql) == 1
    assert inner_sql not in outer_text
    assert root_host.was_closed is False
    assert internal_host.was_closed is False


@pytest.mark.parametrize(
    "test_case",
    [
        DiagnosticsLogTestCase(
            description="owned handler cleanup failure never replaces wrapped behavior",
            debug=False,
            message="original operation failure",
            expected_file_fragments=(),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_owned_handler_close_failure_when_route_exits_then_original_behavior_is_preserved(
    test_case: DiagnosticsLogTestCase, tmp_path: Path
) -> None:
    with patch.object(
        SafeDiagnosticFileHandler,
        "close",
        Mock(side_effect=OSError("controlled close failure")),
    ):
        with configure_diagnostics(target_dir=tmp_path / "return", debug=False):
            logging.getLogger("sqlbuild.cleanup").debug("return path")
        with pytest.raises(RuntimeError, match=test_case.message):
            with configure_diagnostics(target_dir=tmp_path / "raise", debug=False):
                raise RuntimeError(test_case.message)

    assert test_case.expected_file_fragments == ()
