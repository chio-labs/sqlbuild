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

_VIRTUAL_PROJECT_TOML: str = """name = "loader_waffle_shop_virtual"
adapter = "duckdb"
environment_mode = "virtual"
default_environment = "dev"

[connection]
database = "loader_waffle_shop_virtual.duckdb"

[settings]
default_audit_severity = "warn"

[defaults]
materialized = "table"

[environments.dev]
schema = "dev"
defer_sources_to = "dev"

[environments.dev.state]
backend = "duckdb"
schema = "sqlbuild_state"
unsuffixed_virtual_env = "dev"
allow_reset = true

[environments.dev.state.connection]
database = "loader_waffle_shop_state.duckdb"
"""

_VIRTUAL_FACT_WAFFLE_ORDERS_SQL: str = """MODEL (
  materialized table,
  columns (
    order_id (nullable false, audits [not_null, unique]),
    revenue_cents (nullable false, audits [not_null]),
  ),
);

SELECT
  o.order_id,
  o.customer_id,
  c.plan_name,
  o.waffle_type,
  p.waffle_category,
  o.quantity,
  o.price_cents,
  o.quantity * o.price_cents AS revenue_cents,
  o.load_seq
FROM __source("raw_orders") o
LEFT JOIN __source("raw_customers") c ON o.customer_id = c.customer_id
LEFT JOIN __seed("waffle_price_tiers") p ON o.waffle_type = p.waffle_type
"""

_VIRTUAL_TEST_FACT_WAFFLE_ORDERS_SQL: str = """TEST();

WITH
__source__raw_orders AS (
  SELECT
    1 AS order_id,
    10 AS customer_id,
    'classic' AS waffle_type,
    2 AS quantity,
    600 AS price_cents,
    1 AS load_seq
),
__source__raw_customers AS (
  SELECT
    10 AS customer_id,
    'plus' AS plan_name,
    1 AS load_seq
),
__seed__waffle_price_tiers AS (
  SELECT 'classic' AS waffle_type, 'standard' AS waffle_category
),
__expected__fact_waffle_orders AS (
  SELECT
    1 AS order_id,
    10 AS customer_id,
    'plus' AS plan_name,
    'classic' AS waffle_type,
    'standard' AS waffle_category,
    2 AS quantity,
    600 AS price_cents,
    1200 AS revenue_cents,
    1 AS load_seq
),
__assert__revenue_is_non_negative AS (
  SELECT *
  FROM __ref("fact_waffle_orders")
  WHERE revenue_cents < 0
)
SELECT 1
"""

_VIRTUAL_SCENARIO_CUSTOMER_REVENUE_SQL: str = """SCENARIO (
  description: "Customer revenue includes seed-backed waffle categories",
  tags: ["virtual", "example"]
);

WITH
__source__raw_orders AS (
  SELECT
    1 AS order_id,
    10 AS customer_id,
    'classic' AS waffle_type,
    2 AS quantity,
    600 AS price_cents,
    1 AS load_seq
  UNION ALL
  SELECT
    2 AS order_id,
    10 AS customer_id,
    'blueberry' AS waffle_type,
    1 AS quantity,
    750 AS price_cents,
    1 AS load_seq
),
__source__raw_customers AS (
  SELECT
    10 AS customer_id,
    'plus' AS plan_name,
    1 AS load_seq
),
__seed__waffle_price_tiers AS (
  SELECT 'classic' AS waffle_type, 'standard' AS waffle_category
  UNION ALL
  SELECT 'blueberry' AS waffle_type, 'fruit' AS waffle_category
),
__expected__customer_revenue AS (
  SELECT
    10 AS customer_id,
    'plus' AS plan_name,
    1950 AS revenue_cents,
    2 AS order_count
),
__assert__no_negative_customer_revenue AS (
  SELECT *
  FROM __ref("customer_revenue")
  WHERE revenue_cents < 0
)
SELECT 1
"""

_VIRTUAL_SEED_SCHEMA_YML: str = """seeds:
  - name: waffle_price_tiers
    description: Waffle category lookup used by the virtual playground.
    columns:
      - name: waffle_type
        type: VARCHAR
      - name: waffle_category
        type: VARCHAR
"""

_VIRTUAL_SEED_CSV: str = """waffle_type,waffle_category
classic,standard
blueberry,fruit
chocolate,dessert
"""

_VIRTUAL_README: str = """# SQLBuild Virtual Environments Playground

This project is a local DuckDB playground for SQLBuild virtual environments. It is
self-contained and does not require warehouse credentials.

Virtual environments are an advanced, state-backed workflow. This playground uses a
local DuckDB state database so you can try the lifecycle without operating shared
infrastructure.

## Try It

Initialize the state store:

```bash
sqb state init
```

Build the default `dev` virtual environment:

```bash
sqb build
```

Create a branch-like virtual environment:

```bash
sqb build --virtual-env pr
```

Modify a model, then rebuild only the branch:

```bash
sqb build --virtual-env pr
```

Run the project checks:

```bash
sqb test
sqb audit
sqb scenario test
```

Compare the branch with `dev`:

```bash
sqb diff dev:pr --schema-only
```

Promote the branch into `dev`:

```bash
sqb promote --from pr --to dev
```

Inspect and roll back checkpoints:

```bash
sqb state checkpoints list --virtual-env dev
sqb rollback --virtual-env dev
```

## What This Shows

- DuckDB-backed local virtual environment execution
- A local DuckDB state store
- Branch-like virtual environments with `--virtual-env`
- Low-copy promotion through versioned pointers and logical views
- Checkpoint-backed rollback
- Loader-backed waffle shop models without external services
- A seed lookup that is loaded before virtual model execution
- Unit test, audit, and scenario commands that exercise the generated project
"""

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

_RIVERS_DEFINITIONS: str = '''"""Rivers definitions for the SQLBuild waffle shop playground."""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import rivers as rs

from sqlbuild.integrations.rivers import SqlBuildProject, sqlbuild_assets

PROJECT_DIR = Path(__file__).resolve().parent.parent
SQLBUILD_PROJECT = SqlBuildProject(project_dir=PROJECT_DIR)

if __name__ == "__main__":
    SQLBUILD_PROJECT.prepare()
else:
    SQLBUILD_PROJECT.prepare_if_dev()


@sqlbuild_assets(project=SQLBUILD_PROJECT)
def waffle_shop_assets(context: Any) -> Iterator[Any]:
    completed = subprocess.run(
        ["sqb", "build"],
        cwd=PROJECT_DIR,
        capture_output=True,
        check=False,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr or completed.stdout)
    for output_name in context.output_selection:
        yield rs.Materialization(output_name=output_name)


repo = rs.CodeRepository(
    assets=[waffle_shop_assets],
    jobs=[
        rs.Job(
            name="waffle_shop",
            assets=[waffle_shop_assets],
            executor=rs.Executor.in_process(),
        ),
    ],
    default_executor=rs.Executor.in_process(),
)


if __name__ == "__main__":
    result = repo.get_job("waffle_shop").execute()
    raise SystemExit(0 if result.success else 1)
'''

_RIVERS_README: str = """# SQLBuild + Rivers playground

This directory contains a Rivers repository definition for the generated SQLBuild
waffle shop project.

## Run Rivers

Install SQLBuild with the Rivers extra, then start Rivers from the project root:

```bash
uv add "sqlbuild[rivers]"
uv run rivers dev rivers_pipeline.definitions
```

You can also run a local materialization directly:

```bash
uv run python rivers_pipeline/definitions.py
```

The repository defines a `waffle_shop` job for UI-triggered materialization.

The definitions use `SqlBuildProject.prepare_if_dev()` to generate `target/sqlbuild_dag.json`
when `rivers dev` starts with `RIVERS_DEPLOYMENT=dev`.
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
        _LOADER_WAFFLE_SHOP_TEMPLATE
        if template in ("loader_waffle_shop", "virtual")
        else _WAFFLE_SHOP_TEMPLATE
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
    if template == "rivers":
        _write_rivers_template_files(target_dir=target_dir)
    if template == "virtual":
        _write_virtual_template_files(target_dir=target_dir)


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


def _write_rivers_template_files(*, target_dir: Path) -> None:
    rivers_dir: Path = target_dir / "rivers_pipeline"
    rivers_dir.mkdir()
    (rivers_dir / "__init__.py").write_text(
        '"""Rivers playground definitions package."""\n', encoding="utf-8"
    )
    (rivers_dir / "definitions.py").write_text(_RIVERS_DEFINITIONS, encoding="utf-8")
    (rivers_dir / "README.md").write_text(_RIVERS_README, encoding="utf-8")


def _write_virtual_template_files(*, target_dir: Path) -> None:
    (target_dir / "sqlbuild_project.toml").write_text(_VIRTUAL_PROJECT_TOML, encoding="utf-8")
    (target_dir / "README.md").write_text(_VIRTUAL_README, encoding="utf-8")
    (target_dir / "models/fact_waffle_orders.sql").write_text(
        _VIRTUAL_FACT_WAFFLE_ORDERS_SQL, encoding="utf-8"
    )
    seeds_dir: Path = target_dir / "seeds"
    seeds_dir.mkdir()
    (seeds_dir / "lookups.yml").write_text(_VIRTUAL_SEED_SCHEMA_YML, encoding="utf-8")
    (seeds_dir / "waffle_price_tiers.csv").write_text(_VIRTUAL_SEED_CSV, encoding="utf-8")
    unit_tests_dir: Path = target_dir / "tests" / "unit"
    unit_tests_dir.mkdir(parents=True)
    (unit_tests_dir / "test_fact_waffle_orders.sql").write_text(
        _VIRTUAL_TEST_FACT_WAFFLE_ORDERS_SQL, encoding="utf-8"
    )
    scenarios_dir: Path = target_dir / "tests" / "scenarios"
    scenarios_dir.mkdir(parents=True)
    (scenarios_dir / "customer_revenue_minimal.sql").write_text(
        _VIRTUAL_SCENARIO_CUSTOMER_REVENUE_SQL, encoding="utf-8"
    )
