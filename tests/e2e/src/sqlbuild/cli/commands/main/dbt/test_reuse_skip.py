from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.dbt._test_types import DbtReuseSkipE2ETestCase
from tests.e2e.src.sqlbuild.cli.commands.main.dbt.helpers import (
    prepare_dbt_reuse_fatal_macro_project,
    prepare_dbt_reuse_skip_current_branch_project,
    prepare_dbt_reuse_skip_non_git_project,
    skip_unless_dbt_is_runnable,
)
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import run_sqb

pytestmark: pytest.MarkDecorator = pytest.mark.dbt


@pytest.mark.parametrize(
    "test_case",
    [
        DbtReuseSkipE2ETestCase(
            description="reuse_from in a non-git project skips reuse with a warning and builds",
            expected_returncode=0,
            expected_stdout_fragments=(
                "dbt reuse-from-production is enabled but inactive",
                "not in a git repository",
                "Plan ready",
            ),
            expected_stderr_fragments=(),
        )
    ],
    ids=["reuse_from in a non-git project skips reuse with a warning and builds"],
)
def test_given_reuse_from_in_non_git_project_when_building_then_skips_with_warning(
    test_case: DbtReuseSkipE2ETestCase,
    tmp_path: Path,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_reuse_skip_non_git_project(tmp_path=tmp_path)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "dbt", "build", "--select", "orders"),
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_returncode, result.stdout + result.stderr
    fragment: str
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        DbtReuseSkipE2ETestCase(
            description="reuse_from git_ref equal to current branch skips with a warning",
            expected_returncode=0,
            expected_stdout_fragments=(
                "dbt reuse-from-production is enabled but inactive",
                "the configured production ref",
                "Plan ready",
            ),
            expected_stderr_fragments=(),
        )
    ],
    ids=["reuse_from git_ref equal to current branch skips with a warning"],
)
def test_given_reuse_from_ref_is_current_branch_when_building_then_skips_with_warning(
    test_case: DbtReuseSkipE2ETestCase,
    tmp_path: Path,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_reuse_skip_current_branch_project(tmp_path=tmp_path)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "dbt", "build", "--select", "orders"),
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_returncode, result.stdout + result.stderr
    fragment: str
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        DbtReuseSkipE2ETestCase(
            description="reuse compile failure stays fatal and is not swallowed",
            expected_returncode=1,
            expected_stdout_fragments=(),
            expected_stderr_fragments=("dbt reuse_from compile failed",),
        )
    ],
    ids=["reuse compile failure stays fatal and is not swallowed"],
)
def test_given_reuse_compile_failure_when_building_then_errors_not_skipped(
    test_case: DbtReuseSkipE2ETestCase,
    tmp_path: Path,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_reuse_fatal_macro_project(tmp_path=tmp_path)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "dbt", "build", "--select", "orders"),
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_returncode, result.stdout + result.stderr
    output: str = result.stdout + result.stderr
    fragment: str
    for fragment in test_case.expected_stderr_fragments:
        assert fragment in output
