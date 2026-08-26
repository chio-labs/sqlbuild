"""Installed-style subprocess coverage for both scope console aliases."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.scope._test_types import ScopeE2eCase
from tests.e2e.src.sqlbuild.cli.commands.main.scope.helpers import run_scope_alias


@pytest.mark.parametrize(
    "test_case", (ScopeE2eCase("aliases", 0),), ids=lambda case: case.description
)
def test_given_minimal_project_when_running_scope_aliases_then_outputs_are_offline_and_stable(
    tmp_path: Path, test_case: ScopeE2eCase
) -> None:
    project_dir: Path = tmp_path / "project"
    (project_dir / "models").mkdir(parents=True)
    (project_dir / "sqlbuild_project.toml").write_text(
        'name = "scope_e2e"\nadapter = "duckdb"\n', encoding="utf-8"
    )
    (project_dir / "models" / "orders.sql").write_text(
        "MODEL();\nSELECT 1 AS id\n", encoding="utf-8"
    )

    first: subprocess.CompletedProcess[str] = run_scope_alias(
        alias="sqb", project_dir=project_dir, args=("model:orders", "--json")
    )
    second: subprocess.CompletedProcess[str] = run_scope_alias(
        alias="sqb", project_dir=project_dir, args=("model:orders", "--json")
    )
    text: subprocess.CompletedProcess[str] = run_scope_alias(
        alias="sqlbuild", project_dir=project_dir, args=("model:orders",)
    )
    prospective: subprocess.CompletedProcess[str] = run_scope_alias(
        alias="sqb", project_dir=project_dir, args=("--at", "models/new/")
    )
    (project_dir / "macros").mkdir()
    (project_dir / "macros" / "broken.py").write_text("def broken(:\n", encoding="utf-8")
    broken: subprocess.CompletedProcess[str] = run_scope_alias(
        alias="sqb", project_dir=project_dir, args=("model:orders", "--json", "--no-cache")
    )

    assert first.returncode == second.returncode == text.returncode == test_case.expected_exit_code
    assert first.stdout.encode() == second.stdout.encode()
    assert json.loads(first.stdout)["schema_version"] == 1
    assert first.stderr == second.stderr == text.stderr == ""
    assert "Scope\n  Target: model:orders" in text.stdout
    assert prospective.returncode == 1
    assert "prospective, directory" in prospective.stdout
    assert "Completeness: partial" in prospective.stdout
    assert broken.returncode == 1
    assert json.loads(broken.stdout)["resource"]["identity"] == "model:orders"
    assert json.loads(broken.stdout)["complete"] is False


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
