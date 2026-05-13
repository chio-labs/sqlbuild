from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from _pytest.capture import CaptureResult

from sqlbuild.cli.commands.main.dbt import run_dbt_command
from sqlbuild.integrations.dbt.models import DbtInteropPlan
from sqlbuild.integrations.dbt.types import DbtInteropCommand
from tests.unit.src.sqlbuild.cli.commands.main.dbt._test_types import (
    DbtExecutionWrapperTestCase,
    DbtPlanProgressTestCase,
)
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

EXECUTION_WRAPPER_TEST_CASES: list[DbtExecutionWrapperTestCase] = [
    DbtExecutionWrapperTestCase(
        description="dbt run strips local json and verbose flags before execution",
        command_name="run",
        args=("--json", "--verbose", "--select", "tag:nightly"),
        expected_forwarded_args=("--select", "tag:nightly"),
        expected_progress_stream_name="stderr",
    ),
    DbtExecutionWrapperTestCase(
        description="dbt build keeps human output on stdout",
        command_name="build",
        args=("--select", "tag:nightly"),
        expected_forwarded_args=("--select", "tag:nightly"),
        expected_progress_stream_name="stdout",
    ),
    DbtExecutionWrapperTestCase(
        description="dbt test strips local json and verbose flags before execution",
        command_name="test",
        args=("--json", "--verbose", "--select", "test_type:data"),
        expected_forwarded_args=("--select", "test_type:data"),
        expected_progress_stream_name="stderr",
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

    exit_code: int = run_dbt_command(
        command=DbtInteropCommand.PLAN,
        project_dir=Path("/project"),
        args=args,
        no_color=True,
    )

    captured: CaptureResult[str] = capsys.readouterr()
    assert exit_code == 0
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in captured.out
    for fragment in test_case.expected_stderr_fragments:
        assert fragment in captured.err


@pytest.mark.parametrize(
    "test_case",
    EXECUTION_WRAPPER_TEST_CASES,
    ids=[case.description for case in EXECUTION_WRAPPER_TEST_CASES],
)
def test_given_dbt_execution_command_when_running_then_routes_expected_stream_and_args(
    test_case: DbtExecutionWrapperTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_calls: list[tuple[DbtInteropCommand, tuple[str, ...], object]] = []

    def execute_dbt_interop_from_project(
        *,
        command: DbtInteropCommand,
        project_dir: Path,
        args: tuple[str, ...],
        on_progress: Callable[[str], None],
        progress_stream: object,
        dbt_stdout_stream: object,
        use_color: bool,
        verbose: bool,
        json_output: bool,
    ) -> int:
        del project_dir, on_progress, dbt_stdout_stream, use_color, verbose, json_output
        captured_calls.append((command, args, progress_stream))
        return 0

    monkeypatch.setattr(
        "sqlbuild.cli.commands.main.dbt.execute_dbt_interop_from_project",
        execute_dbt_interop_from_project,
    )

    exit_code: int = run_dbt_command(
        command=DbtInteropCommand(test_case.command_name),
        project_dir=Path("/project"),
        args=test_case.args,
        no_color=True,
    )

    assert exit_code == 0
    assert captured_calls[0][1] == test_case.expected_forwarded_args
    expected_stream: object = (
        sys.stderr if test_case.expected_progress_stream_name == "stderr" else sys.stdout
    )
    assert captured_calls[0][2] is expected_stream
