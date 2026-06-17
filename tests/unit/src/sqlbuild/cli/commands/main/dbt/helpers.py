from __future__ import annotations

from pathlib import Path

from sqlbuild.integrations.dbt.helpers.plan import build_dbt_interop_plan
from sqlbuild.integrations.dbt.models import DbtInteropPlan, DbtInteropSelectionResult
from sqlbuild.integrations.dbt.types import DbtInteropCommand
from tests.unit.src.sqlbuild.cli.commands.main.dbt._test_types import DbtAutoInitTestCase


def build_empty_dbt_plan() -> DbtInteropPlan:
    """Build a minimal dbt interop plan for CLI output tests."""

    return build_dbt_interop_plan(
        command=DbtInteropCommand.PLAN,
        dbt_command_argv=("dbt", "ls"),
        dbt_ls_nodes=(),
        sqlbuild_command_argvs=(),
        selection=DbtInteropSelectionResult(),
    )


def prepare_dbt_auto_init_dirs(*, test_case: DbtAutoInitTestCase, tmp_path: Path) -> Path:
    """Prepare current and sibling SQLBuild config files for auto-init tests."""

    dbt_project_dir: Path = tmp_path / "dbt_project"
    dbt_project_dir.mkdir()
    sibling_sqlbuild_dir: Path = tmp_path / "sqlbuild_project"
    if test_case.has_current_sqlbuild_project:
        write_minimal_sqlbuild_project(dbt_project_dir)
    if test_case.has_sibling_sqlbuild_project:
        sibling_sqlbuild_dir.mkdir()
        write_minimal_sqlbuild_project(sibling_sqlbuild_dir)
    return dbt_project_dir


def write_minimal_sqlbuild_project(project_dir: Path) -> None:
    """Write a minimal SQLBuild project config for wrapper tests."""

    (project_dir / "sqlbuild_project.toml").write_text(
        'name = "demo"\nadapter = "duckdb"\n', encoding="utf-8"
    )
