from __future__ import annotations

from pathlib import Path

from sqlbuild.spec.contracts.models import DbtConfig, ProjectConfig


def write_duckdb_dbt_workspace(root: Path) -> None:
    """Write a dbt project and a DuckDB profile under `root`."""

    (root / "dbt_project").mkdir()
    (root / "profiles").mkdir()
    (root / "dbt_project" / "dbt_project.yml").write_text(
        "name: shop\nprofile: shop\n", encoding="utf-8"
    )
    (root / "profiles" / "profiles.yml").write_text(
        "shop:\n  target: dev\n  outputs:\n    dev:\n      type: duckdb\n"
        "      path: warehouse.duckdb\n      schema: main\n",
        encoding="utf-8",
    )


def dbt_workspace_project_config(*, adapter_name: str) -> ProjectConfig:
    """A project config pointing at the workspace's dbt project and profiles."""

    return ProjectConfig(
        name="shop",
        adapter=adapter_name,
        dbt=DbtConfig(project_dir="dbt_project", profiles_dir="profiles"),
    )
