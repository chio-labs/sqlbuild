"""Tests for planning progress output."""

from __future__ import annotations

from io import StringIO

import pytest

from sqlbuild.cli.commands.main.shared.helpers.progress.planning import (
    PlanningProgressReporter,
    _is_planning_completion_message,
)
from sqlbuild.shared.helpers.colors import dim
from tests.unit.src.sqlbuild.cli.commands.main.shared.helpers._test_types import (
    PlanningCompletionMessageTestCase,
    PlanningFinishTestCase,
    PlanningProgressTestCase,
)

PLANNING_PROGRESS_TEST_CASES: list[PlanningProgressTestCase] = [
    PlanningProgressTestCase(
        description="writes each planning message on its own line",
        messages=("Inspecting warehouse state...", "Generating plan..."),
        expected_output="Inspecting warehouse state...\nGenerating plan...\n",
    ),
    PlanningProgressTestCase(
        description="completes planned status messages before later output",
        messages=(
            "Planning dbt reuse from git ref 'main'...",
            "Planned dbt reuse from git ref 'main'. (0.10s)",
            "Plan ready",
        ),
        expected_output=(
            "Planning dbt reuse from git ref 'main'...\n"
            "Planned dbt reuse from git ref 'main'. (0.10s)\n"
            "Plan ready\n"
        ),
    ),
    PlanningProgressTestCase(
        description="dims planning messages when color is enabled",
        messages=("Inspecting warehouse state...",),
        expected_output=f"{dim('Inspecting warehouse state...')}\n",
        use_color=True,
    ),
    PlanningProgressTestCase(
        description="completes cloned status messages before later output",
        messages=(
            "Applying clone plan...",
            "Applied clone plan. (0.10s)",
            "sqb clone",
        ),
        expected_output=("Applying clone plan...\nApplied clone plan. (0.10s)\nsqb clone\n"),
    ),
]
PLANNING_COMPLETION_MESSAGE_TEST_CASES: list[PlanningCompletionMessageTestCase] = [
    PlanningCompletionMessageTestCase(
        description="treats planned dbt reuse as completion",
        message="Planned dbt reuse from git ref 'main'. (0.10s)",
        expected_is_completion=True,
    ),
    PlanningCompletionMessageTestCase(
        description="keeps planning dbt reuse as active status",
        message="Planning dbt reuse from git ref 'main'...",
        expected_is_completion=False,
    ),
    PlanningCompletionMessageTestCase(
        description="treats applied clone plan as completion",
        message="Applied clone plan. (0.10s)",
        expected_is_completion=True,
    ),
]


@pytest.mark.parametrize(
    "test_case",
    PLANNING_PROGRESS_TEST_CASES,
    ids=[case.description for case in PLANNING_PROGRESS_TEST_CASES],
)
def test_given_planning_messages_when_reporting_then_writes_expected_output(
    test_case: PlanningProgressTestCase,
) -> None:
    stream: StringIO = StringIO()
    reporter: PlanningProgressReporter = PlanningProgressReporter(
        stream=stream, use_color=test_case.use_color
    )

    message: str
    for message in test_case.messages:
        reporter.on_progress(message)

    assert stream.getvalue() == test_case.expected_output


@pytest.mark.parametrize(
    "test_case",
    PLANNING_COMPLETION_MESSAGE_TEST_CASES,
    ids=[case.description for case in PLANNING_COMPLETION_MESSAGE_TEST_CASES],
)
def test_given_planning_message_when_classifying_completion_then_returns_expected_result(
    test_case: PlanningCompletionMessageTestCase,
) -> None:
    assert _is_planning_completion_message(test_case.message) == test_case.expected_is_completion


@pytest.mark.parametrize(
    "test_case",
    [
        PlanningFinishTestCase(
            description="closes active planning status with blank line before later output",
            messages_before_finish=("Applying clone plan...",),
            blank_line_after=True,
            messages_after_finish=("sqb clone",),
            expected_output="Applying clone plan...\n\nsqb clone\n",
        )
    ],
    ids=["closes active planning status with blank line before later output"],
)
def test_given_active_planning_status_when_finishing_then_closes_with_blank_line(
    test_case: PlanningFinishTestCase,
) -> None:
    stream: StringIO = StringIO()
    reporter: PlanningProgressReporter = PlanningProgressReporter(stream=stream, use_color=False)

    message: str
    for message in test_case.messages_before_finish:
        reporter.on_progress(message)
    reporter.finish(blank_line_after=test_case.blank_line_after)
    for message in test_case.messages_after_finish:
        reporter.on_progress(message)

    assert stream.getvalue() == test_case.expected_output
