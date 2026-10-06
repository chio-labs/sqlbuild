"""Installed-style subprocess coverage for both scope console aliases."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.scope._test_types import (
    ScopeBareTargetE2eCase,
    ScopeE2eCase,
)
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
        "MODEL(description 'Test model orders.');\nSELECT 1 AS id\n", encoding="utf-8"
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
    assert json.loads(first.stdout)["schema_version"] == 2
    assert "Project discovery  START" in first.stderr
    assert text.stderr == ""
    assert "Scope\n  Target: model:orders" in text.stdout
    assert prospective.returncode == 1
    assert "prospective, directory" in prospective.stdout
    assert "Completeness: partial" in prospective.stdout
    assert broken.returncode == 1
    assert json.loads(broken.stdout)["resource"]["identity"] == "model:orders"
    assert json.loads(broken.stdout)["complete"] is False


@pytest.mark.parametrize(
    "test_case", (ScopeE2eCase("bare model name", 0),), ids=lambda case: case.description
)
def test_given_bare_model_name_when_running_scope_then_matches_the_prefixed_report(
    tmp_path: Path, test_case: ScopeE2eCase
) -> None:
    project_dir: Path = tmp_path / "project"
    (project_dir / "models").mkdir(parents=True)
    (project_dir / "sqlbuild_project.toml").write_text(
        'name = "scope_e2e"\nadapter = "duckdb"\n', encoding="utf-8"
    )
    (project_dir / "models" / "orders.sql").write_text(
        "MODEL(description 'Test model orders.');\nSELECT 1 AS id\n", encoding="utf-8"
    )

    prefixed: subprocess.CompletedProcess[str] = run_scope_alias(
        alias="sqb", project_dir=project_dir, args=("model:orders", "--json")
    )
    bare: subprocess.CompletedProcess[str] = run_scope_alias(
        alias="sqb", project_dir=project_dir, args=("orders", "--json")
    )

    assert prefixed.returncode == bare.returncode == test_case.expected_exit_code, bare.stderr
    assert bare.stdout == prefixed.stdout


@pytest.mark.parametrize(
    "test_case",
    (
        ScopeBareTargetE2eCase(
            description="bare macro name needs its prefix",
            target="cents",
            expected_exit_code=1,
            expected_fragment="scope target 'cents' needs its prefix: macro:cents",
        ),
        ScopeBareTargetE2eCase(
            description="unknown bare name",
            target="missing",
            expected_exit_code=1,
            expected_fragment="unknown scope target 'missing'",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_bare_name_that_is_not_a_resource_when_running_scope_then_fails_clearly(
    tmp_path: Path, test_case: ScopeBareTargetE2eCase
) -> None:
    project_dir: Path = tmp_path / "project"
    (project_dir / "models").mkdir(parents=True)
    (project_dir / "macros").mkdir()
    (project_dir / "sqlbuild_project.toml").write_text(
        'name = "scope_e2e"\nadapter = "duckdb"\n', encoding="utf-8"
    )
    (project_dir / "models" / "orders.sql").write_text(
        "MODEL(description 'Test model orders.');\nSELECT 1 AS id\n", encoding="utf-8"
    )
    (project_dir / "macros" / "cents.py").write_text(
        "def cents(expression: str) -> str:\n    return expression\n", encoding="utf-8"
    )

    result: subprocess.CompletedProcess[str] = run_scope_alias(
        alias="sqb", project_dir=project_dir, args=(test_case.target, "--no-color")
    )

    assert result.returncode == test_case.expected_exit_code
    assert "C960" in result.stderr
    assert test_case.expected_fragment in result.stderr


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
