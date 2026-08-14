from __future__ import annotations

import pytest

from sqlbuild.executor.build._helpers.output import (
    _format_abbreviated_row_count,
    _format_batch_summary_line,
)
from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.executor.scheduling.types import ExecutionStatus
from tests.unit.src.sqlbuild.executor.build._helpers._test_types import (
    AbbreviatedRowCountTestCase,
    BatchSummaryTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        AbbreviatedRowCountTestCase(
            description="exact count below abbreviation threshold",
            count=438,
            expected_output="438 rows",
        ),
        AbbreviatedRowCountTestCase(
            description="single row uses singular label",
            count=1,
            expected_output="1 row",
        ),
        AbbreviatedRowCountTestCase(
            description="count at threshold abbreviates to K",
            count=10_000,
            expected_output="10.0K rows",
        ),
        AbbreviatedRowCountTestCase(
            description="millions abbreviate to M",
            count=32_689_379,
            expected_output="32.7M rows",
        ),
        AbbreviatedRowCountTestCase(
            description="billions abbreviate to B",
            count=1_847_293_612,
            expected_output="1.8B rows",
        ),
        AbbreviatedRowCountTestCase(
            description="just below threshold stays exact",
            count=9_999,
            expected_output="9,999 rows",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_row_count_when_abbreviating_then_matches_expected_format(
    test_case: AbbreviatedRowCountTestCase,
) -> None:
    result: str = _format_abbreviated_row_count(count=test_case.count)

    assert result == test_case.expected_output


@pytest.mark.parametrize(
    "test_case",
    [
        BatchSummaryTestCase(
            description="microbatch result includes batch count size range and rows",
            batch_count=5,
            batch_size="1mo",
            rows_affected=32_689_379,
            cursor_range_start="2014-01-01",
            cursor_range_end="2015-01-01",
            cursor_type="timestamp",
            cursor_grain="day",
            expected_fragments=(
                "5 batches (1mo)",
                "2014-01-01",
                "2014-12-31",
                "32.7M rows",
            ),
        ),
        BatchSummaryTestCase(
            description="microbatch result without rows omits row count",
            batch_count=3,
            rows_affected=None,
            cursor_range_start="2014-01-01",
            cursor_range_end="2014-04-01",
            cursor_type="timestamp",
            cursor_grain="day",
            expected_fragments=("3 batches",),
            expected_absent_fragments=("rows",),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_model_result_when_formatting_batch_summary_then_matches_contract(
    test_case: BatchSummaryTestCase,
) -> None:
    result: ModelExecutionResult = ModelExecutionResult(
        model_name="test_model",
        status=ExecutionStatus.SUCCESS,
        batch_count=test_case.batch_count,
        batch_size=test_case.batch_size,
        rows_affected=test_case.rows_affected,
        cursor_range_start=test_case.cursor_range_start,
        cursor_range_end=test_case.cursor_range_end,
        cursor_type=test_case.cursor_type,
        cursor_grain=test_case.cursor_grain,
    )

    line: str | None = _format_batch_summary_line(model_result=result, use_color=False)

    assert line is not None
    fragment: str
    for fragment in test_case.expected_fragments:
        assert fragment in line
    for fragment in test_case.expected_absent_fragments:
        assert fragment not in line


@pytest.mark.parametrize(
    "test_case",
    [
        BatchSummaryTestCase(
            description="non-microbatch result returns none",
            batch_count=None,
            rows_affected=None,
            cursor_range_start=None,
            cursor_range_end=None,
            cursor_type=None,
            cursor_grain=None,
            expected_fragments=(),
            expected_none=True,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_non_microbatch_result_when_formatting_batch_summary_then_returns_none(
    test_case: BatchSummaryTestCase,
) -> None:
    result: ModelExecutionResult = ModelExecutionResult(
        model_name="test_model",
        status=ExecutionStatus.SUCCESS,
        batch_count=test_case.batch_count,
    )

    line: str | None = _format_batch_summary_line(model_result=result, use_color=False)

    assert (line is None) == test_case.expected_none
