"""Synthetic playground fixture for semantic compilation regression cases."""

import subprocess
from pathlib import Path

import pytest

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
