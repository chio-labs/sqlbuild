"""Tests for diagnostics logging."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from sqlbuild.adapters.duckdb.client import DuckDbAdapter
from sqlbuild.diagnostics.main.configure import configure_diagnostics
from sqlbuild.shared.helpers.diagnostics.logging import diagnostics_context
from tests.unit.src.sqlbuild.diagnostics._test_types import (
    DiagnosticsContextualSqlTestCase,
    DiagnosticsLogTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        DiagnosticsLogTestCase(
            description="writes debug firehose SQL to log file without console output",
            debug=False,
            message="file-only diagnostic",
            expected_file_fragments=(
                "DEBUG unit file-only diagnostic",
                "DEBUG adapter.duckdb execute SQL",
                "-" * 80 + "\nSELECT 1\n" + "-" * 80,
            ),
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
    configure_diagnostics(target_dir=target_dir, debug=test_case.debug)
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
    configure_diagnostics(target_dir=target_dir, debug=test_case.debug)
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
            description="formats multiline SQL as blocks in file and stderr",
            debug=True,
            message="",
            expected_file_fragments=(
                "DEBUG adapter.duckdb execute SQL",
                "CREATE OR REPLACE VIEW main.debug_view AS SELECT\n  1 AS id",
            ),
            expected_console_fragments=(
                "[debug] adapter.duckdb execute sql",
                "CREATE OR REPLACE VIEW main.debug_view AS SELECT\n  1 AS id",
            ),
            expected_absent_file_fragments=("\\n  1 AS id",),
            expected_absent_console_fragments=("\\n  1 AS id",),
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
    configure_diagnostics(target_dir=target_dir, debug=test_case.debug)
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: object = adapter.connect({"database": ":memory:"})
    adapter.execute(
        connection=connection, sql="CREATE OR REPLACE VIEW main.debug_view AS SELECT\n  1 AS id"
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
                "[debug] model daily_revenue phase=promote action=begin_txn execute sql  BEGIN"
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
    configure_diagnostics(target_dir=target_dir, debug=test_case.debug)
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: object = adapter.connect({"database": ":memory:"})

    with diagnostics_context(**test_case.context):
        adapter.execute(connection=connection, sql=test_case.sql)

    adapter.close(connection)

    console_error: str = capsys.readouterr().err

    assert test_case.expected_console_fragment in console_error
