"""E2E coverage for fail-closed Python project layout validation."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.compile._test_types import (
    PythonProjectLayoutCompileTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import prepare_inline_project, run_sqb


@pytest.mark.parametrize(
    "test_case",
    (
        PythonProjectLayoutCompileTestCase(
            description="unsupported project Python root",
            repo_files={
                "sqlbuild_project.toml": 'name = "python_layout"\nadapter = "duckdb"\n',
                "audit_helpers/measurements.py": "def build_cases(): return []\n",
            },
            expected_exit_code=1,
            expected_stderr_fragments=(
                "Unsupported project Python path(s): audit_helpers/measurements.py",
                "Factory support modules, including factories/**/_helpers.py, are allowed",
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_python_under_unsupported_root_when_compiling_then_command_fails_with_path_guidance(
    test_case: PythonProjectLayoutCompileTestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="python_layout",
        repo_files=test_case.repo_files,
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "compile"),
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    assert all(fragment in result.stderr for fragment in test_case.expected_stderr_fragments)


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
