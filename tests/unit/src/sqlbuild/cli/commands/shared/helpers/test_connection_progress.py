"""Tests for warehouse connection progress messages."""

from __future__ import annotations

from io import StringIO

import pytest

from sqlbuild.cli.commands.shared.helpers.progress.connection import (
    ConnectionProgressReporter,
)
from sqlbuild.shared.helpers.output.colors import dim
from tests.unit.src.sqlbuild.cli.commands.shared.helpers._test_types import (
    ConnectionProgressTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ConnectionProgressTestCase(
            description="single connection message omits count",
            connection_count=1,
            elapsed_seconds=0.034,
            expected_start="Connecting to duckdb...",
            expected_complete="Connected to duckdb. (0.03s)",
            expected_error="Failed to connect to duckdb after 0.03s.",
            expected_lines=(
                "Connecting to duckdb...",
                "Connected to duckdb. (0.03s)",
                "Failed to connect to duckdb after 0.03s.",
            ),
        ),
        ConnectionProgressTestCase(
            description="multiple connection message includes count",
            connection_count=8,
            elapsed_seconds=18.424,
            expected_start="Connecting to databricks (8 connections)...",
            expected_complete="Connected to databricks. (18.42s)",
            expected_error="Failed to connect to databricks after 18.42s.",
            expected_lines=(
                "Connecting to databricks (8 connections)...",
                "Connected to databricks. (18.42s)",
                "Failed to connect to databricks after 18.42s.",
            ),
        ),
        ConnectionProgressTestCase(
            description="execution connection completion can add spacing before progress rows",
            connection_count=8,
            elapsed_seconds=10.924,
            expected_start="Connecting to databricks (8 connections)...",
            expected_complete="Connected to databricks. (10.92s)",
            expected_error="Failed to connect to databricks after 10.92s.",
            blank_line_after_complete=True,
            expected_lines=(
                "Connecting to databricks (8 connections)...",
                "Connected to databricks. (10.92s)",
                "",
                "Failed to connect to databricks after 10.92s.",
            ),
        ),
        ConnectionProgressTestCase(
            description="execution connection start can add spacing after pre-connection work",
            connection_count=1,
            elapsed_seconds=0.034,
            expected_start="Connecting to duckdb...",
            expected_complete="Connected to duckdb. (0.03s)",
            expected_error="Failed to connect to duckdb after 0.03s.",
            blank_line_before_start=True,
            expected_lines=(
                "",
                "Connecting to duckdb...",
                "Connected to duckdb. (0.03s)",
                "Failed to connect to duckdb after 0.03s.",
            ),
        ),
        ConnectionProgressTestCase(
            description="connection progress dims start and success when color is enabled",
            connection_count=1,
            elapsed_seconds=0.034,
            expected_start="Connecting to duckdb...",
            expected_complete="Connected to duckdb. (0.03s)",
            expected_error="Failed to connect to duckdb after 0.03s.",
            use_color=True,
            expected_lines=(
                dim("Connecting to duckdb..."),
                dim("Connected to duckdb. (0.03s)"),
                "Failed to connect to duckdb after 0.03s.",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_connection_progress_event_when_reporting_then_writes_expected_message(
    test_case: ConnectionProgressTestCase,
) -> None:
    stream: StringIO = StringIO()
    adapter_name: str = "databricks" if test_case.connection_count > 1 else "duckdb"
    reporter: ConnectionProgressReporter = ConnectionProgressReporter(
        adapter_name=adapter_name,
        stream=stream,
        blank_line_before_start=test_case.blank_line_before_start,
        blank_line_after_complete=test_case.blank_line_after_complete,
        use_color=test_case.use_color,
    )

    reporter.on_connection_start(test_case.connection_count)
    reporter.on_connection_complete(test_case.connection_count, test_case.elapsed_seconds)
    reporter.on_connection_error(test_case.connection_count, test_case.elapsed_seconds)

    assert stream.getvalue().splitlines() == list(test_case.expected_lines)
