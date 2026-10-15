"""Tests for the diagnostics console formatter's duration token."""

from __future__ import annotations

import logging

import pytest

from sqlbuild.diagnostics.classes.diagnostics_console_formatter import (
    DiagnosticsConsoleFormatter,
)
from tests.unit.src.sqlbuild.diagnostics._test_types import ConsoleDurationTestCase


@pytest.mark.parametrize(
    "test_case",
    [
        ConsoleDurationTestCase(
            description="small duration rounds like Python",
            subject="model",
            duration_ms=1005,
            expected_line="[info] model duration=1.00s done",
        ),
        ConsoleDurationTestCase(
            description="duration above 2**63 formats like Python",
            subject="model",
            duration_ms=2**70,
            expected_line="[info] model duration=1180591620717411328.00s done",
        ),
        ConsoleDurationTestCase(
            description="negative duration below -2**63 formats like Python",
            subject="model",
            duration_ms=-(2**80),
            expected_line="[info] model duration=-1208925819614629199872.00s done",
        ),
        ConsoleDurationTestCase(
            description="bool duration is an int",
            subject="model",
            duration_ms=True,
            expected_line="[info] model duration=0.00s done",
        ),
        ConsoleDurationTestCase(
            description="non-integer duration is ignored",
            subject="model",
            duration_ms=1.5,
            expected_line="[info] model done",
        ),
        ConsoleDurationTestCase(
            description="non-string subject ignores an oversized duration",
            subject=5,
            duration_ms=2**70,
            expected_line="[info] exec done",
        ),
        ConsoleDurationTestCase(
            description="duration too large for a float is omitted instead of raising",
            subject="model",
            duration_ms=10**400,
            expected_line="[info] model done",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_duration_field_when_formatting_console_line_then_matches_python_rendering(
    test_case: ConsoleDurationTestCase,
) -> None:
    record: logging.LogRecord = logging.makeLogRecord(
        {
            "name": "sqlbuild.exec",
            "levelname": "INFO",
            "msg": "done",
            "sqlbuild_subject": test_case.subject,
            "sqlbuild_duration_ms": test_case.duration_ms,
        }
    )

    line: str = DiagnosticsConsoleFormatter().format(record)

    assert line == test_case.expected_line, test_case.description
