"""Formatting every repository example project changes layout only."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.format._test_types import (
    ExampleProjectFormatTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.format.helpers import compiled_contract
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import REPO_ROOT, run_sqb


@pytest.mark.parametrize(
    "test_case",
    [
        ExampleProjectFormatTestCase("website waffle shop", "website/examples/waffle-shop"),
        ExampleProjectFormatTestCase("website tidy shop", "website/examples/tidy-shop"),
        ExampleProjectFormatTestCase("website hero shop", "website/examples/hero-shop"),
        ExampleProjectFormatTestCase("e2e waffle shop", "tests/e2e/fixtures/waffle_shop"),
    ],
    ids=lambda case: case.description,
)
def test_given_example_project_when_formatting_then_compiled_contract_is_unchanged(
    test_case: ExampleProjectFormatTestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = tmp_path / "project"
    shutil.copytree(REPO_ROOT / test_case.relative_path, project_dir)
    before: dict[str, list[tuple[object, ...]]] = compiled_contract(project_dir=project_dir)

    formatted: subprocess.CompletedProcess[str] = run_sqb(
        project_dir=project_dir, command=("--no-color", "format")
    )
    checked: subprocess.CompletedProcess[str] = run_sqb(
        project_dir=project_dir, command=("--no-color", "format", "--check")
    )
    after: dict[str, list[tuple[object, ...]]] = compiled_contract(project_dir=project_dir)

    assert formatted.returncode == test_case.expected_format_exit_code, formatted.stderr
    assert "format-unsafe" not in formatted.stdout + formatted.stderr
    assert checked.returncode == test_case.expected_format_exit_code, checked.stderr
    assert ", 0 changed)" in checked.stderr
    assert after == before
