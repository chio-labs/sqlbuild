from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from sqlbuild.cli.commands.main.workspace._playground import run_playground
from sqlbuild.cli.commands.models import PlaygroundCommandRequest
from tests.e2e.src.sqlbuild.cli.commands.main.playground._test_types import (
    PythonNodesPlaygroundLifecycleTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import run_sqb


@pytest.mark.parametrize(
    "test_case",
    [
        PythonNodesPlaygroundLifecycleTestCase(
            description="python nodes playground runs plan build and check lifecycle",
            project_name="python_nodes_demo",
            expected_plan_fragments=(
                "raw_orders",
                "fact_orders",
                "Python read-side",
            ),
            expected_build_fragments=(
                "prepare_raw_orders",
                "raw_orders",
                "fact_orders",
                "orders_export",
                "\u2713 Completed successfully",
            ),
            expected_check_fragments=(
                "check_orders_export",
                "PASS",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_python_nodes_playground_when_running_lifecycle_then_it_succeeds(
    test_case: PythonNodesPlaygroundLifecycleTestCase,
    tmp_path: Path,
) -> None:
    assert (
        run_playground(
            PlaygroundCommandRequest(
                project_dir=tmp_path, target_path=test_case.project_name, template="python_nodes"
            )
        )
        == 0
    )
    project_dir: Path = tmp_path / test_case.project_name

    plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=(
            "--no-color",
            "plan",
            "--select",
            "+fact_orders",
            "--select",
            "+orders_export",
        ),
        project_dir=project_dir,
    )
    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=(
            "--no-color",
            "build",
            "--select",
            "+fact_orders",
            "--select",
            "+orders_export",
        ),
        project_dir=project_dir,
    )
    check_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "check", "--select", "check_orders_export"),
        project_dir=project_dir,
    )

    plan_output: str = plan_result.stdout + plan_result.stderr
    assert plan_result.returncode == 0
    for expected_fragment in test_case.expected_plan_fragments:
        assert expected_fragment in plan_output

    build_output: str = build_result.stdout + build_result.stderr
    assert build_result.returncode == 0
    for expected_fragment in test_case.expected_build_fragments:
        assert expected_fragment in build_output

    check_output: str = check_result.stdout + check_result.stderr
    assert check_result.returncode == 0
    for expected_fragment in test_case.expected_check_fragments:
        assert expected_fragment in check_output
