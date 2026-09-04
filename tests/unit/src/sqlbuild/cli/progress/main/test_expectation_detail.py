"""Tests for SQL expected-output diagnostic formatting."""

import pytest

from sqlbuild.cli.progress.main._expectation_detail import format_expectation_detail
from sqlbuild.executor.testing.models import SqlTestDifferenceSample, StepResult
from sqlbuild.executor.testing.types import SqlTestOutcome
from tests.unit.src.sqlbuild.cli.progress.main._test_types import ExpectationDetailTestCase


@pytest.mark.parametrize(
    "test_case",
    (
        ExpectationDetailTestCase(
            description="two-way samples show directional rows",
            step_result=StepResult(
                model_name="orders",
                outcome=SqlTestOutcome.FAIL,
                actual_row_count=2,
                expected_row_count=1,
                mismatched_row_count=1,
                unexpected_row_count=1,
                missing_row_count=1,
                unexpected_samples=(
                    SqlTestDifferenceSample(values=(("id", "2"), ("status", "unexpected"))),
                ),
                missing_samples=(
                    SqlTestDifferenceSample(values=(("id", "1"), ("status", "expected"))),
                ),
            ),
            expected_fragments=(
                "unexpected=1",
                "missing=1",
                "row counts actual=2 expected=1",
                "unexpected sample 1: id=2, status=unexpected",
                "missing sample 1: id=1, status=expected",
            ),
        ),
        ExpectationDetailTestCase(
            description="duplicate-only difference shows row counts",
            step_result=StepResult(
                model_name="orders",
                outcome=SqlTestOutcome.FAIL,
                actual_row_count=2,
                expected_row_count=1,
                unexpected_row_count=0,
                missing_row_count=0,
            ),
            expected_fragments=(
                "unexpected=0",
                "missing=0",
                "row counts actual=2 expected=1",
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_failure_when_formatting_expectation_then_diagnostics_are_shown(
    test_case: ExpectationDetailTestCase,
) -> None:
    detail: str = format_expectation_detail(test_case.step_result)

    for expected_fragment in test_case.expected_fragments:
        assert expected_fragment in detail
