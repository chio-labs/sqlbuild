from __future__ import annotations

import pytest

from tests.unit.src.sqlbuild.cli.progress.classes._test_types import StepProgressCase
from tests.unit.src.sqlbuild.cli.progress.classes.helpers import (
    complete_step_normally,
    fail_step,
    project_resource_step,
)


@pytest.mark.parametrize(
    "test_case",
    (
        StepProgressCase(
            description="redirected output hides passing step rows by default",
            tty=False,
            debug=False,
            expected_line_prefixes=("  table     orders START", "  table     orders OK "),
        ),
        StepProgressCase(
            description="terminal output keeps only the resource result row by default",
            tty=True,
            debug=False,
            expected_line_prefixes=("  table     orders OK ",),
        ),
        StepProgressCase(
            description="redirected output shows passing step rows with debug",
            tty=False,
            debug=True,
            expected_line_prefixes=(
                "  table     orders START",
                "    Create staging relation  START",
                "    Create staging relation  OK  (",
                "  table     orders OK ",
            ),
        ),
        StepProgressCase(
            description="terminal output shows start and step rows with debug",
            tty=True,
            debug=True,
            expected_line_prefixes=(
                "  table     orders START",
                "    Create staging relation  START",
                "    Create staging relation  OK  (",
                "  table     orders OK ",
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_passing_resource_step_when_projected_then_step_rows_follow_debug_flag(
    test_case: StepProgressCase,
) -> None:
    lines: tuple[str, ...] = project_resource_step(
        test_case=test_case, finish_step=complete_step_normally
    )

    assert len(lines) == len(test_case.expected_line_prefixes), lines
    assert all(
        line.startswith(prefix)
        for line, prefix in zip(lines, test_case.expected_line_prefixes, strict=True)
    ), lines


@pytest.mark.parametrize(
    "test_case",
    (
        StepProgressCase(
            description="redirected output still reports a failed step by default",
            tty=False,
            debug=False,
            expected_line_prefixes=(
                "  table     orders START",
                "    Create staging relation  FAIL  (",
                "  table     orders OK ",
            ),
        ),
        StepProgressCase(
            description="terminal output still reports a failed step by default",
            tty=True,
            debug=False,
            expected_line_prefixes=(
                "    Create staging relation  FAIL  (",
                "  table     orders OK ",
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_failed_resource_step_when_projected_without_debug_then_failure_row_is_shown(
    test_case: StepProgressCase,
) -> None:
    lines: tuple[str, ...] = project_resource_step(test_case=test_case, finish_step=fail_step)

    assert len(lines) == len(test_case.expected_line_prefixes), lines
    assert all(
        line.startswith(prefix)
        for line, prefix in zip(lines, test_case.expected_line_prefixes, strict=True)
    ), lines
