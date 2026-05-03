"""Tests for runtime SQL statement recording."""

from __future__ import annotations

import pytest

from sqlbuild.executor.shared.classes.statement_recorder import StatementRecorder
from tests.unit.src.sqlbuild.executor.shared.helpers._test_types import (
    StatementRecorderTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        StatementRecorderTestCase(
            description="records individual and grouped statements in order",
            statements=("CREATE TABLE x AS SELECT 1", "DROP TABLE y"),
            expected_snapshot=("CREATE TABLE x AS SELECT 1", "DROP TABLE y"),
        )
    ],
    ids=["records individual and grouped statements in order"],
)
def test_given_recorded_statements_when_snapshotting_then_returns_expected_tuple(
    test_case: StatementRecorderTestCase,
) -> None:
    recorder: StatementRecorder = StatementRecorder()

    recorder.record(test_case.statements[0])
    recorder.record_many(test_case.statements[1:])
    result: tuple[str, ...] = recorder.snapshot()

    assert result == test_case.expected_snapshot
