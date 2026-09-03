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
            description="init scaffolds typed hook and audit directories",
            expected_exit_code=0,
            expected_paths=(
                "sqlbuild_project.toml",
                "hooks/sql",
                "hooks/sql/.gitkeep",
                "hooks/python",
                "hooks/python/.gitkeep",
                "audits/generic",
                "audits/generic/.gitkeep",
                "audits/singular",
                "audits/singular/.gitkeep",
            ),
            expected_output_fragments=(
                "SQLBuild project created",
                "Add SQL hooks to hooks/sql/, Python hooks to hooks/python/",
                "reusable audits to audits/generic/",
                "standalone audits to audits/singular/",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_empty_project_directory_when_running_init_then_typed_resource_directories_are_scaffolded(
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
