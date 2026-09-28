"""Synthetic playground fixture for semantic compilation regression cases."""

import subprocess
from pathlib import Path

import pytest

from scripts.cold_compile_performance.main.assert_required_cgroup_memory_limit import (
    assert_required_cgroup_memory_limit,
)
from tests.e2e.src.sqlbuild.cli.commands.main.compile.helpers import (
    prepare_inspection_benchmark_project,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import run_sqb


@pytest.fixture(scope="session")
def semantic_playground(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root: Path = tmp_path_factory.mktemp("semantic_playground")
    project: Path = root / "orders_project"
    result: subprocess.CompletedProcess[str] = run_sqb(
        project_dir=root, command=("playground", str(project))
    )
    assert result.returncode == 0, result.stdout + result.stderr
    typed: Path = Path(__file__).parent / "fixtures" / "semantic" / "typed_orders.sql"
    (project / "models" / "staging" / "stg_orders_typed.sql").write_text(
        typed.read_text(encoding="utf-8"), encoding="utf-8"
    )
    return project


@pytest.fixture(scope="module")
def inspection_benchmark_project(tmp_path_factory: pytest.TempPathFactory) -> Path:
    assert_required_cgroup_memory_limit()
    project_dir: Path = tmp_path_factory.mktemp("inspection") / "semantic_inspection"
    prepare_inspection_benchmark_project(project_dir=project_dir)
    return project_dir
