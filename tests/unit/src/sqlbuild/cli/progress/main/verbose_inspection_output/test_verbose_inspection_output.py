"""Verbose inspection lines are single-line, truncated, and go to stderr only."""

from __future__ import annotations

import pytest
from _pytest.capture import CaptureResult

from sqlbuild.adapter.relations.main.record_inspection_query import record_inspection_query
from sqlbuild.adapter.relations.models import InspectionQueryRecord
from sqlbuild.cli.progress.classes.verbose_inspection_writer import VerboseInspectionWriter
from sqlbuild.cli.progress.main.verbose_inspection_output import verbose_inspection_output
from tests.unit.src.sqlbuild.cli.progress.main.verbose_inspection_output._test_types import (
    VerboseInspectionFormatTestCase,
    VerboseInspectionOutputTestCase,
)

_LONG_SQL: str = (
    'SELECT table_name, column_name, data_type FROM "ANALYTICS".information_schema.columns\n'
    "WHERE table_schema = 'STAGING' AND table_catalog = 'ANALYTICS' "
    + "ORDER BY table_name, ordinal_position "
    * 8
)


@pytest.mark.parametrize(
    "test_case",
    [
        VerboseInspectionFormatTestCase(
            description="long multi-line SQL is collapsed and truncated",
            sql=_LONG_SQL,
            row_count=652,
            error=None,
            expected_fragments=("0.42s", "652 rows", "information_schema.columns WHERE", "..."),
            expected_maximum_length=200,
        ),
        VerboseInspectionFormatTestCase(
            description="single row is singular",
            sql="SELECT CAST(MAX(ordered_at) AS VARCHAR) AS _max FROM analytics.marts.orders",
            row_count=1,
            error=None,
            expected_fragments=(" 1 row ", "FROM analytics.marts.orders"),
            expected_maximum_length=200,
        ),
        VerboseInspectionFormatTestCase(
            description="failure shows the error instead of a row count",
            sql="SHOW COLUMNS IN TABLE analytics.raw.orders",
            row_count=None,
            error="Object does not exist\nor not authorized",
            expected_fragments=("failed: Object does not exist or not authorized", "SHOW COLUMNS"),
            expected_maximum_length=200,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_inspection_record_when_formatting_then_renders_one_bounded_line(
    test_case: VerboseInspectionFormatTestCase,
) -> None:
    line: str = VerboseInspectionWriter.format_record(
        record=InspectionQueryRecord(
            sql=test_case.sql,
            elapsed_seconds=0.42,
            row_count=test_case.row_count,
            error=test_case.error,
        )
    )

    assert "\n" not in line
    assert len(line) <= test_case.expected_maximum_length
    for fragment in test_case.expected_fragments:
        assert fragment in line


@pytest.mark.parametrize(
    "test_case",
    [
        VerboseInspectionOutputTestCase(
            description="enabled output writes each read and a total to stderr",
            enabled=True,
            records=(("SELECT 1", 0.5, 3), ("SELECT 2", 0.25, 0)),
            expected_stderr_lines=(
                "  inspect   0.50s  3 rows  SELECT 1",
                "  inspect   0.25s  0 rows  SELECT 2",
                "Inspection queries: 2 (0.75s cumulative query time)",
            ),
        ),
        VerboseInspectionOutputTestCase(
            description="disabled output writes nothing",
            enabled=False,
            records=(("SELECT 1", 0.5, 3),),
            expected_stderr_lines=(),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_verbose_setting_when_recording_reads_then_writes_only_inside_context_to_stderr(
    test_case: VerboseInspectionOutputTestCase, capsys: pytest.CaptureFixture[str]
) -> None:
    with verbose_inspection_output(enabled=test_case.enabled):
        for sql, elapsed, rows in test_case.records:
            record_inspection_query(
                record=InspectionQueryRecord(sql=sql, elapsed_seconds=elapsed, row_count=rows)
            )
    record_inspection_query(
        record=InspectionQueryRecord(sql="SELECT 3", elapsed_seconds=0.1, row_count=0)
    )

    captured: CaptureResult[str] = capsys.readouterr()
    assert captured.out == ""
    assert tuple(captured.err.splitlines()) == test_case.expected_stderr_lines


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
