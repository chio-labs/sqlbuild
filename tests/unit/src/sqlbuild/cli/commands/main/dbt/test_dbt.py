from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from sqlbuild.cli.commands.main.dbt import run_dbt_plan
from sqlbuild.integrations.dbt.models import DbtInteropPlan
from tests.unit.src.sqlbuild.cli.commands.main.dbt._test_types import DbtPlanProgressTestCase
from tests.unit.src.sqlbuild.cli.commands.main.dbt.helpers import build_empty_dbt_plan

PROGRESS_TEST_CASES: list[DbtPlanProgressTestCase] = [
    DbtPlanProgressTestCase(
        description="human output writes progress and plan to stdout",
        json_output=False,
        expected_stdout_fragments=(
            "Compiling dbt project...",
            "Generated dbt interop plan.",
            "Plan ready",
        ),
        expected_stderr_fragments=(),
    ),
    DbtPlanProgressTestCase(
        description="json output writes progress to stderr and json to stdout",
        json_output=True,
        expected_stdout_fragments=('"command": "plan"',),
        expected_stderr_fragments=(
            "Compiling dbt project...",
            "Generated dbt interop plan.",
        ),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    PROGRESS_TEST_CASES,
    ids=[case.description for case in PROGRESS_TEST_CASES],
)
def test_given_dbt_plan_when_running_then_writes_progress_to_expected_stream(
    test_case: DbtPlanProgressTestCase,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def plan_dbt_interop_from_project(
        *,
        project_dir: Path,
        args: tuple[str, ...],
        on_progress: Callable[[str], None],
        progress_stream: object,
        use_color: bool,
    ) -> DbtInteropPlan:
        del project_dir, args, progress_stream, use_color
        assert callable(on_progress)
        on_progress("Compiling dbt project...")
        on_progress("Generated dbt interop plan. (0.01s)")
        return build_empty_dbt_plan()

    monkeypatch.setattr(
        "sqlbuild.cli.commands.main.dbt.plan_dbt_interop_from_project",
        plan_dbt_interop_from_project,
    )
    args: tuple[str, ...] = ("--json",) if test_case.json_output else ()

    exit_code: int = run_dbt_plan(project_dir=Path("/project"), args=args, no_color=True)

    captured = capsys.readouterr()
    assert exit_code == 0
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in captured.out
    for fragment in test_case.expected_stderr_fragments:
        assert fragment in captured.err
