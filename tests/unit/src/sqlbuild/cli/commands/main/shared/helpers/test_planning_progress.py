"""Tests for planning progress output."""

from __future__ import annotations

from io import StringIO

import pytest

from sqlbuild.cli.commands.main.shared.helpers.planning_progress import PlanningProgressReporter
from sqlbuild.shared.helpers.colors import dim
from tests.unit.src.sqlbuild.cli.commands.main.shared.helpers._test_types import (
    PlanningProgressTestCase,
)

PLANNING_PROGRESS_TEST_CASES: list[PlanningProgressTestCase] = [
    PlanningProgressTestCase(
        description="writes each planning message on its own line",
        messages=("Inspecting warehouse state...", "Generating plan..."),
        expected_output="Inspecting warehouse state...\nGenerating plan...\n",
    ),
    PlanningProgressTestCase(
        description="dims planning messages when color is enabled",
        messages=("Inspecting warehouse state...",),
        expected_output=f"{dim('Inspecting warehouse state...')}\n",
        use_color=True,
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
