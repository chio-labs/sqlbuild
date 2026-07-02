"""E2E tests for sqb init."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.init._test_types import InitE2ETestCase
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import run_sqb


@pytest.mark.parametrize(
    "test_case",
    [
        InitE2ETestCase(
            description="init scaffolds hooks directory",
            expected_exit_code=0,
            expected_paths=("sqlbuild_project.toml", "hooks", "hooks/.gitkeep"),
            expected_output_fragments=(
                "SQLBuild project created",
                "Add hooks to hooks/",
            ),
        )
    ],
    ids=["init scaffolds hooks directory"],
)
def test_given_empty_project_directory_when_running_init_then_hooks_directory_is_scaffolded(
    test_case: InitE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = tmp_path / "init_hooks_project"
    project_dir.mkdir()

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "init"),
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    for fragment in test_case.expected_output_fragments:
        assert fragment in result.stdout
    for expected_path in test_case.expected_paths:
        assert (project_dir / expected_path).exists()
