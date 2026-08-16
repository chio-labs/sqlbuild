from __future__ import annotations

import pytest

from sqlbuild.executor.run._helpers.materializations.microbatch import _reported_rows_affected
from tests.unit.src.sqlbuild.executor.run._helpers._test_types import (
    ReportedRowsAffectedTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ReportedRowsAffectedTestCase(
            description="known zero remains a reported zero",
            total_rows=0,
            row_count_known=True,
            expected_rows_affected=0,
        ),
        ReportedRowsAffectedTestCase(
            description="unavailable count remains absent",
            total_rows=0,
            row_count_known=False,
            expected_rows_affected=None,
        ),
        ReportedRowsAffectedTestCase(
            description="known positive count remains reported",
            total_rows=42,
            row_count_known=True,
            expected_rows_affected=42,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_accumulated_rows_when_reporting_then_preserves_known_zero(
    test_case: ReportedRowsAffectedTestCase,
) -> None:
    result: int | None = _reported_rows_affected(
        total_rows=test_case.total_rows,
        row_count_known=test_case.row_count_known,
    )

    assert result == test_case.expected_rows_affected
