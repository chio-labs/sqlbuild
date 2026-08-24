"""Tests for warehouse connection progress messages."""

from __future__ import annotations

from io import StringIO

import pytest

from sqlbuild.cli.progress.classes.connection_progress_reporter import (
    ConnectionProgressReporter,
)
from sqlbuild.presentation.classes.cli_style import CliStyle
from tests.unit.src.sqlbuild.cli.commands.shared._helpers._test_types import (
    ConnectionProgressTestCase,
)


class _InteractiveStringIO(StringIO):
    def isatty(self) -> bool:
        return True


@pytest.mark.parametrize(
    "test_case",
    [
        ConnectionProgressTestCase(
            description="single connection message omits count",
            adapter_name="duckdb",
            connection_count=1,
            elapsed_seconds=0.034,
            expected_start="Connecting to duckdb...",
            expected_complete="\u2713 Warehouse connected  duckdb  (0.03s)",
            expected_error="\u2717 Warehouse connection failed  duckdb  (after 0.03s)",
            expected_lines=(
                "Connecting to duckdb...",
                "\u2713 Warehouse connected  duckdb  (0.03s)",
                "\u2717 Warehouse connection failed  duckdb  (after 0.03s)",
            ),
        ),
        ConnectionProgressTestCase(
            description="multiple connection message includes count",
            adapter_name="databricks",
            connection_count=8,
            elapsed_seconds=18.424,
            expected_start="Connecting to databricks (8 connections)...",
            expected_complete="\u2713 Warehouse connected  databricks  (18.42s)",
            expected_error="\u2717 Warehouse connection failed  databricks  (after 18.42s)",
            expected_lines=(
                "Connecting to databricks (8 connections)...",
                "\u2713 Warehouse connected  databricks  (18.42s)",
                "\u2717 Warehouse connection failed  databricks  (after 18.42s)",
            ),
        ),
        ConnectionProgressTestCase(
            description="execution connection completion can add spacing before progress rows",
            adapter_name="databricks",
            connection_count=8,
            elapsed_seconds=10.924,
            expected_start="Connecting to databricks (8 connections)...",
            expected_complete="\u2713 Warehouse connected  databricks  (10.92s)",
            expected_error="\u2717 Warehouse connection failed  databricks  (after 10.92s)",
            blank_line_after_complete=True,
            expected_lines=(
                "Connecting to databricks (8 connections)...",
                "\u2713 Warehouse connected  databricks  (10.92s)",
                "",
                "\u2717 Warehouse connection failed  databricks  (after 10.92s)",
            ),
        ),
        ConnectionProgressTestCase(
            description="execution connection start can add spacing after pre-connection work",
            adapter_name="duckdb",
            connection_count=1,
            elapsed_seconds=0.034,
            expected_start="Connecting to duckdb...",
            expected_complete="\u2713 Warehouse connected  duckdb  (0.03s)",
            expected_error="\u2717 Warehouse connection failed  duckdb  (after 0.03s)",
            blank_line_before_start=True,
            expected_lines=(
                "",
                "Connecting to duckdb...",
                "\u2713 Warehouse connected  duckdb  (0.03s)",
                "\u2717 Warehouse connection failed  duckdb  (after 0.03s)",
            ),
        ),
        ConnectionProgressTestCase(
            description="connection progress dims start and success when color is enabled",
            adapter_name="duckdb",
            connection_count=1,
            elapsed_seconds=0.034,
            expected_start="Connecting to duckdb...",
            expected_complete="\u2713 Warehouse connected  duckdb  (0.03s)",
            expected_error="\u2717 Warehouse connection failed  duckdb  (after 0.03s)",
            use_color=True,
            expected_lines=(
                CliStyle(use_color=True).muted("Connecting to duckdb..."),
                "\033[32m\u2713\033[0m Warehouse connected  "
                + CliStyle(use_color=True).muted("duckdb  (0.03s)"),
                "\033[38;5;167m\u2717\033[0m \033[38;5;167m\033[1mWarehouse connection failed\033[0m  "
                + CliStyle(use_color=True).muted("duckdb  (after 0.03s)"),
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_connection_progress_event_when_reporting_then_writes_expected_message(
    test_case: ConnectionProgressTestCase,
) -> None:
    stream: StringIO = _InteractiveStringIO()
    reporter: ConnectionProgressReporter = ConnectionProgressReporter(
        adapter_name=test_case.adapter_name,
        stream=stream,
        blank_line_before_start=test_case.blank_line_before_start,
        blank_line_after_complete=test_case.blank_line_after_complete,
        use_color=test_case.use_color,
    )

    reporter.on_connection_start(test_case.connection_count)
    reporter.on_connection_complete(
        connection_count=test_case.connection_count, elapsed_seconds=test_case.elapsed_seconds
    )
    reporter.on_connection_error(
        connection_count=test_case.connection_count, elapsed_seconds=test_case.elapsed_seconds
    )

    assert stream.getvalue().splitlines() == list(test_case.expected_lines)
