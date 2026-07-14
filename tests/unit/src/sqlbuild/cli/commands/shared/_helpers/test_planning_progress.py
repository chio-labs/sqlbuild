"""Tests for planning progress output."""

from __future__ import annotations

from io import StringIO

import pytest

from sqlbuild.cli.progress.classes.planning_progress_reporter import (
    PlanningProgressReporter,
    _is_planning_completion_message,
)
from sqlbuild.presentation.classes.cli_style import CliStyle
from tests.unit.src.sqlbuild.cli.commands.shared._helpers._test_types import (
    PlanningCompletionMessageTestCase,
    PlanningFinishTestCase,
    PlanningProgressTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
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
            expected_output=f"{CliStyle(use_color=True).muted('Inspecting warehouse state...')}\n",
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
        PlanningProgressTestCase(
            description="persists dbt post-build state phases on their own lines",
            messages=(
                "Finalizing dbt run...",
                "Finalized dbt run.",
                "Recording dbt fingerprints...",
                "Recorded dbt fingerprints. (0.10s)",
            ),
            expected_output=(
                "Finalizing dbt run...\n"
                "Finalized dbt run.\n"
                "Recording dbt fingerprints...\n"
                "Recorded dbt fingerprints. (0.10s)\n"
            ),
        ),
    ],
    ids=lambda case: case.description,
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
    [
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
        PlanningCompletionMessageTestCase(
            description="treats recorded dbt fingerprints as completion",
            message="Recorded dbt fingerprints. (0.10s)",
            expected_is_completion=True,
        ),
        PlanningCompletionMessageTestCase(
            description="treats finalized dbt run as completion",
            message="Finalized dbt run.",
            expected_is_completion=True,
        ),
        PlanningCompletionMessageTestCase(
            description="keeps recording dbt fingerprints as active status",
            message="Recording dbt fingerprints...",
            expected_is_completion=False,
        ),
    ],
    ids=lambda case: case.description,
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
    ids=lambda case: case.description,
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
