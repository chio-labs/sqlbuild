from __future__ import annotations

import json
import subprocess
from pathlib import Path
from shutil import copytree

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import REPO_ROOT

DBT_INTEROP_FIXTURE_DIR: Path = REPO_ROOT / "tests" / "e2e" / "fixtures" / "dbt_interop"


def skip_unless_dbt_is_runnable() -> None:
    """Skip e2e dbt tests when the dbt CLI is unavailable."""

    result: subprocess.CompletedProcess[str] = subprocess.run(
        ("dbt", "--version"),
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode != 0:
        pytest.skip(f"dbt CLI is not runnable: {result.stderr or result.stdout}")


def prepare_dbt_interop_project(*, tmp_path: Path) -> Path:
    """Copy the reusable dbt interop fixture and return its SQLBuild project root."""

    root_dir: Path = tmp_path / "dbt_interop"
    copytree(DBT_INTEROP_FIXTURE_DIR, root_dir)
    db_path: Path = root_dir / "sqlbuild_project" / "dbt_interop.duckdb"
    if db_path.exists():
        db_path.unlink()
    return root_dir / "sqlbuild_project"


def static_dbt_interop_project_dir() -> Path:
    """Return the repository fixture SQLBuild project path."""

    return DBT_INTEROP_FIXTURE_DIR / "sqlbuild_project"


def load_json_stdout(stdout: str) -> dict[str, object]:
    """Load JSON command output."""

    payload: object = json.loads(stdout)
    assert isinstance(payload, dict)
    return payload
