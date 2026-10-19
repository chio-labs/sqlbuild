"""E2E coverage for the exit code of `sqb plan`."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.plan._test_types import PlanExitCodeE2ETestCase
from tests.e2e.src.sqlbuild.cli.commands.main.plan.helpers import (
    NAME_CLAIM_ERROR,
    RECLAIMED_NAME,
    REMOVABLE_MIGRATION_WARNING,
    migrated_project,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import run_sqb


@pytest.mark.parametrize(
    "test_case",
    [
        PlanExitCodeE2ETestCase(
            description="a plan with only warnings exits 0",
            added_files={},
            plan_args=(),
            expected_exit_code=0,
            expected_output_fragments=(
                REMOVABLE_MIGRATION_WARNING,
                "\u2713 Plan complete  1 selected",
            ),
        ),
        PlanExitCodeE2ETestCase(
            description="a plan with an error finding exits 1 and states failure",
            added_files=RECLAIMED_NAME,
            plan_args=(),
            expected_exit_code=1,
            expected_output_fragments=(
                NAME_CLAIM_ERROR,
                "\u2717 Plan failed with errors  2 selected",
            ),
        ),
        PlanExitCodeE2ETestCase(
            description="a json plan with an error finding exits 1",
            added_files=RECLAIMED_NAME,
            plan_args=("--json",),
            expected_exit_code=1,
            expected_output_fragments=(NAME_CLAIM_ERROR,),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_plan_findings_when_planning_then_exit_code_reflects_errors(
    test_case: PlanExitCodeE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = migrated_project(tmp_path)
    relative_path: str
    contents: str
    for relative_path, contents in test_case.added_files.items():
        (project_dir / relative_path).write_text(contents, encoding="utf-8")

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan", *test_case.plan_args),
        project_dir=project_dir,
    )

    output: str = result.stdout + result.stderr
    assert result.returncode == test_case.expected_exit_code, test_case.description + output
    assert all(fragment in output for fragment in test_case.expected_output_fragments), (
        test_case.description + output
    )
