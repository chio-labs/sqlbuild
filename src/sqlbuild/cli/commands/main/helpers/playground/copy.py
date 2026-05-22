"""Copy packaged playground templates to user projects."""

from __future__ import annotations

from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path

from sqlbuild.cli.commands.main.helpers.playground.constants import PLAYGROUND_TEMPLATE_VALUES
from sqlbuild.cli.commands.main.shared.exceptions import CliUserError

_TEMPLATE_PACKAGE: str = "sqlbuild.playground"
_WAFFLE_SHOP_TEMPLATE: str = "templates/waffle_shop"
_LOADER_WAFFLE_SHOP_TEMPLATE: str = "templates/loader_waffle_shop"

_DAGSTER_DEFINITIONS: str = '''"""Dagster definitions for the SQLBuild waffle shop playground."""

from pathlib import Path

import dagster as dg

from sqlbuild.integrations.dagster import (
    SqlBuildCliResource,
    SqlBuildProject,
    sqlbuild_assets,
    sqlbuild_scenario_checks,
)

PROJECT_DIR = Path(__file__).resolve().parent.parent
SQLBUILD_PROJECT = SqlBuildProject(project_dir=PROJECT_DIR)

SQLBUILD_PROJECT.prepare_if_dev()


@sqlbuild_assets(
    project=SQLBUILD_PROJECT,
    required_resource_keys={"sqb"},
    include_scenario_checks=False,
)
def waffle_shop_assets(context: dg.AssetExecutionContext):
    yield from context.resources.sqb.cli(["build"], context=context).stream()


@sqlbuild_scenario_checks(
    project=SQLBUILD_PROJECT,
    required_resource_keys={"sqb"},
)
def waffle_shop_scenarios(context: dg.AssetCheckExecutionContext):
    yield from context.resources.sqb.cli(["scenario", "test"], context=context).stream()


defs = dg.Definitions(
    assets=[waffle_shop_assets],
    asset_checks=[waffle_shop_scenarios],
    resources={"sqb": SqlBuildCliResource(project_dir=SQLBUILD_PROJECT)},
)
'''

_DAGSTER_README: str = """# SQLBuild + Dagster playground

This directory contains a Dagster definitions file for the generated SQLBuild waffle shop project.

## Run Dagster

Install SQLBuild with the Dagster extra, then start Dagster from the project root:

```bash
uv add "sqlbuild[dagster]"
DAGSTER_IS_DEV_CLI=1 uv run dagster dev -f dagster/definitions.py
```

Open the Dagster UI, materialize the `waffle_shop_assets` asset group, then run the scenario checks.

The definitions use `SqlBuildProject.prepare_if_dev()` to generate `target/sqlbuild_dag.json`
when Dagster starts in dev mode.
"""


def create_playground_project(*, target_dir: Path, template: str = "waffle_shop") -> None:
    """Create a DuckDB-backed waffle shop playground project."""

    if target_dir.exists():
        raise CliUserError(
            f"playground target already exists: {target_dir}",
            code="C701",
            help="choose a new directory or remove the existing one",
        )
    if template not in PLAYGROUND_TEMPLATE_VALUES:
        raise CliUserError(
            f"unknown playground template: {template}",
            code="C703",
            help=f"choose one of: {', '.join(PLAYGROUND_TEMPLATE_VALUES)}",
        )

    template_path: str = (
        _LOADER_WAFFLE_SHOP_TEMPLATE if template == "loader_waffle_shop" else _WAFFLE_SHOP_TEMPLATE
    )
    template_root: Traversable = files(_TEMPLATE_PACKAGE).joinpath(template_path)
    if not template_root.is_dir():
        raise CliUserError(
            "packaged playground template is missing",
            code="C702",
            help="reinstall SQLBuild or report a packaging issue",
        )
    _copy_tree(source=template_root, target=target_dir)
    if template == "dagster":
        _write_dagster_template_files(target_dir=target_dir)


def _copy_tree(*, source: Traversable, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=False)
    child: Traversable
    for child in source.iterdir():
        child_target: Path = target / _generated_name(child.name)
        if child.is_dir():
            _copy_tree(source=child, target=child_target)
            continue
        child_target.write_bytes(child.read_bytes())


def _generated_name(template_name: str) -> str:
    if template_name.endswith(".py.txt"):
        return template_name.removesuffix(".txt")
    return template_name


def _write_dagster_template_files(*, target_dir: Path) -> None:
    dagster_dir: Path = target_dir / "dagster"
    dagster_dir.mkdir()
    (dagster_dir / "definitions.py").write_text(_DAGSTER_DEFINITIONS, encoding="utf-8")
    (dagster_dir / "README.md").write_text(_DAGSTER_README, encoding="utf-8")
