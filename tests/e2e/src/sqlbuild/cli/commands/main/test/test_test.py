"""E2E tests for sqb test command."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import (
    prepare_waffle_shop,
    run_sqb,
)
from tests.e2e.src.sqlbuild.cli.commands.main.test._test_types import SqlTestE2ETestCase


@pytest.mark.parametrize(
    "test_case",
    [
        SqlTestE2ETestCase(
            description="test runs SQL unit tests and all pass",
            expected_exit_code=0,
            expected_stdout_fragment="PASS=1",
        ),
    ],
    ids=["test runs SQL unit tests and all pass"],
)
def test_given_waffle_shop_project_when_running_test_then_all_tests_pass(
    test_case: SqlTestE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_waffle_shop(tmp_path)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "test"), project_dir=project_dir
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    assert test_case.expected_stdout_fragment in result.stdout
