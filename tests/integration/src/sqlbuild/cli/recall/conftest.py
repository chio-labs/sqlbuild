"""Built synthetic projects for local Recall tests."""

import subprocess
from pathlib import Path

import pytest

from tests.integration.src.sqlbuild.cli.recall.helpers import run, write_project


@pytest.fixture(name="built_project")
def fixture_built_project(tmp_path: Path) -> tuple[Path, subprocess.CompletedProcess[bytes]]:
    project_dir: Path = write_project(tmp_path / "orders_shop")
    built: subprocess.CompletedProcess[bytes] = run(project_dir, "build")
    assert built.returncode == 0, built.stderr.decode(errors="replace")
    return project_dir, built
