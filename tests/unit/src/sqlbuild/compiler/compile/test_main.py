from __future__ import annotations

import re
from pathlib import Path

import pytest

from sqlbuild.compiler.compile.main import build_compile_inputs
from sqlbuild.compiler.compile.models import CompileProjectInputs
from sqlbuild.compiler.discovery.main import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from tests.unit.src.sqlbuild.compiler.compile._test_helpers import (
    base_repo_files,
    write_repo_files,
)
from tests.unit.src.sqlbuild.compiler.compile._test_types import (
    BuildCompileInputsErrorTestCase,
    BuildCompileInputsTestCase,
)

TEST_CASES: list[BuildCompileInputsTestCase] = [
    BuildCompileInputsTestCase(
        description="attaches schema metadata to matching models and seeds and normalizes sources",
        repo_files=base_repo_files()
        | {
            "sqlbuild_project.yml": """
name: demo
adapter: duckdb
default_environment: dev

connection:
  path: base.db
  warehouse: default_wh

vars:
  shared: project
  project_only: present

defaults:
  materialized: table
  schema: analytics
  batch_size: 1h

path_defaults:
  models/staging:
    materialized: view
    schema: staging
  models/staging/nested:
    schema: nested

environments:
  dev:
    connection:
      warehouse: dev_wh
    vars:
      shared: environment
      env_only: present
""".strip()
            + "\n",
            "sqlbuild_local.yml": """
environment: dev
vars:
  shared: local
  local_only: present
""".strip()
            + "\n",
            "models/staging/orders.sql": "MODEL ();\n\nselect 1\n",
            "models/staging/nested/orders_enriched.sql": """
MODEL (
  materialized: incremental,
  batch_size: 30m,
);

select 1
""".strip()
            + "\n",
            "models/staging/schema.yml": """
models:
  - name: orders
    columns:
      - name: order_id
        type: VARCHAR
""".strip()
            + "\n",
            "seeds/schema.yml": """
seeds:
  - name: country_codes
    columns:
      - name: country_code
        type: VARCHAR
      - name: country_name
        type: VARCHAR
""".strip()
            + "\n",
            "seeds/country_codes.csv": "country_code,country_name\nUS,United States\n",
            "sources/raw.yml": """
sources:
  - name: raw_orders
    schema: public
    table: orders
""".strip()
            + "\n",
        },
        selected_environment=None,
        cli_vars={"shared": "cli", "cli_only": "present"},
        run_id=None,
        expected_model_schema_names=(None, "orders"),
        expected_model_config_values=(
            {"materialized": "incremental", "schema": "nested", "batch_size": "30m"},
            {"materialized": "view", "schema": "staging", "batch_size": "1h"},
        ),
        expected_model_query_sqls=("select 1", "select 1"),
        expected_model_path_defaults=("models/staging/nested", "models/staging"),
        expected_seed_names=("country_codes",),
        expected_source_names=("raw_orders",),
        expected_effective_environment_name="dev",
        expected_effective_connection={"path": "base.db", "warehouse": "dev_wh"},
        expected_effective_vars={
            "shared": "cli",
            "project_only": "present",
            "env_only": "present",
            "local_only": "present",
            "cli_only": "present",
        },
    ),
    BuildCompileInputsTestCase(
        description="allows models with no matching schema metadata",
        repo_files=base_repo_files() | {"models/staging/orders.sql": "MODEL ();\n\nselect 1\n"},
        selected_environment=None,
        cli_vars={},
        run_id=None,
        expected_model_schema_names=(None,),
        expected_model_config_values=({},),
        expected_model_query_sqls=("select 1",),
        expected_model_path_defaults=(None,),
        expected_seed_names=(),
        expected_source_names=(),
        expected_effective_environment_name=None,
        expected_effective_connection={},
        expected_effective_vars={},
    ),
    BuildCompileInputsTestCase(
        description="prefers selected environment over local and project defaults",
        repo_files=base_repo_files()
        | {
            "sqlbuild_project.yml": """
name: demo
adapter: duckdb
default_environment: dev

connection:
  path: base.db
  warehouse: default_wh

vars:
  shared: project

environments:
  dev:
    connection:
      warehouse: dev_wh
    vars:
      shared: dev
  prod:
    connection:
      warehouse: prod_wh
      role: transformer
    vars:
      shared: prod
      prod_only: present
""".strip()
            + "\n",
            "sqlbuild_local.yml": """
environment: dev
vars:
  shared: local
""".strip()
            + "\n",
            "models/staging/orders.sql": "MODEL ();\n\nselect 1\n",
        },
        selected_environment="prod",
        cli_vars={},
        run_id=None,
        expected_model_schema_names=(None,),
        expected_model_config_values=({},),
        expected_model_query_sqls=("select 1",),
        expected_model_path_defaults=(None,),
        expected_seed_names=(),
        expected_source_names=(),
        expected_effective_environment_name="prod",
        expected_effective_connection={
            "path": "base.db",
            "warehouse": "prod_wh",
            "role": "transformer",
        },
        expected_effective_vars={"shared": "local", "prod_only": "present"},
    ),
    BuildCompileInputsTestCase(
        description="prefers local environment over project default when cli is absent",
        repo_files=base_repo_files()
        | {
            "sqlbuild_project.yml": """
name: demo
adapter: duckdb
default_environment: prod

connection:
  path: base.db

environments:
  dev:
    connection:
      warehouse: dev_wh
    vars:
      active: dev
  prod:
    connection:
      warehouse: prod_wh
    vars:
      active: prod
""".strip()
            + "\n",
            "sqlbuild_local.yml": """
environment: dev
""".strip()
            + "\n",
            "models/staging/orders.sql": "MODEL ();\n\nselect 1\n",
        },
        selected_environment=None,
        cli_vars=None,
        run_id=None,
        expected_model_schema_names=(None,),
        expected_model_config_values=({},),
        expected_model_query_sqls=("select 1",),
        expected_model_path_defaults=(None,),
        expected_seed_names=(),
        expected_source_names=(),
        expected_effective_environment_name="dev",
        expected_effective_connection={"path": "base.db", "warehouse": "dev_wh"},
        expected_effective_vars={"active": "dev"},
    ),
    BuildCompileInputsTestCase(
        description="returns no effective environment when none is configured anywhere",
        repo_files=base_repo_files()
        | {
            "sqlbuild_project.yml": """
name: demo
adapter: duckdb

connection:
  path: base.db

vars:
  project_only: present
""".strip()
            + "\n",
            "sqlbuild_local.yml": """
vars:
  local_only: present
""".strip()
            + "\n",
            "models/staging/orders.sql": "MODEL ();\n\nselect 1\n",
        },
        selected_environment=None,
        cli_vars={"cli_only": "present"},
        run_id=None,
        expected_model_schema_names=(None,),
        expected_model_config_values=({},),
        expected_model_query_sqls=("select 1",),
        expected_model_path_defaults=(None,),
        expected_seed_names=(),
        expected_source_names=(),
        expected_effective_environment_name=None,
        expected_effective_connection={"path": "base.db"},
        expected_effective_vars={
            "project_only": "present",
            "local_only": "present",
            "cli_only": "present",
        },
    ),
    BuildCompileInputsTestCase(
        description="preserves project connection when environment has no connection override",
        repo_files=base_repo_files()
        | {
            "sqlbuild_project.yml": """
name: demo
adapter: duckdb
default_environment: dev

connection:
  path: base.db
  warehouse: default_wh

environments:
  dev:
    vars:
      active: dev
""".strip()
            + "\n",
            "models/staging/orders.sql": "MODEL ();\n\nselect 1\n",
        },
        selected_environment=None,
        cli_vars=None,
        run_id=None,
        expected_model_schema_names=(None,),
        expected_model_config_values=({},),
        expected_model_query_sqls=("select 1",),
        expected_model_path_defaults=(None,),
        expected_seed_names=(),
        expected_source_names=(),
        expected_effective_environment_name="dev",
        expected_effective_connection={"path": "base.db", "warehouse": "default_wh"},
        expected_effective_vars={"active": "dev"},
    ),
    BuildCompileInputsTestCase(
        description="preserves non environment vars when selected environment defines none",
        repo_files=base_repo_files()
        | {
            "sqlbuild_project.yml": """
name: demo
adapter: duckdb
default_environment: dev

vars:
  project_only: present

environments:
  dev:
    connection:
      warehouse: dev_wh
""".strip()
            + "\n",
            "sqlbuild_local.yml": """
vars:
  local_only: present
""".strip()
            + "\n",
            "models/staging/orders.sql": "MODEL ();\n\nselect 1\n",
        },
        selected_environment=None,
        cli_vars={"cli_only": "present"},
        run_id=None,
        expected_model_schema_names=(None,),
        expected_model_config_values=({},),
        expected_model_query_sqls=("select 1",),
        expected_model_path_defaults=(None,),
        expected_seed_names=(),
        expected_source_names=(),
        expected_effective_environment_name="dev",
        expected_effective_connection={"warehouse": "dev_wh"},
        expected_effective_vars={
            "project_only": "present",
            "local_only": "present",
            "cli_only": "present",
        },
    ),
    BuildCompileInputsTestCase(
        description="allows environment only connection when project connection is empty",
        repo_files=base_repo_files()
        | {
            "sqlbuild_project.yml": """
name: demo
adapter: duckdb
default_environment: dev

environments:
  dev:
    connection:
      path: env.db
      warehouse: dev_wh
""".strip()
            + "\n",
            "models/staging/orders.sql": "MODEL ();\n\nselect 1\n",
        },
        selected_environment=None,
        cli_vars=None,
        run_id=None,
        expected_model_schema_names=(None,),
        expected_model_config_values=({},),
        expected_model_query_sqls=("select 1",),
        expected_model_path_defaults=(None,),
        expected_seed_names=(),
        expected_source_names=(),
        expected_effective_environment_name="dev",
        expected_effective_connection={"path": "env.db", "warehouse": "dev_wh"},
        expected_effective_vars={},
    ),
    BuildCompileInputsTestCase(
        description="allows env local and cli vars when project vars are empty",
        repo_files=base_repo_files()
        | {
            "sqlbuild_project.yml": """
name: demo
adapter: duckdb
default_environment: dev

environments:
  dev:
    vars:
      shared: env
      env_only: present
""".strip()
            + "\n",
            "sqlbuild_local.yml": """
vars:
  shared: local
  local_only: present
""".strip()
            + "\n",
            "models/staging/orders.sql": "MODEL ();\n\nselect 1\n",
        },
        selected_environment=None,
        cli_vars={"shared": "cli", "cli_only": "present"},
        run_id=None,
        expected_model_schema_names=(None,),
        expected_model_config_values=({},),
        expected_model_query_sqls=("select 1",),
        expected_model_path_defaults=(None,),
        expected_seed_names=(),
        expected_source_names=(),
        expected_effective_environment_name="dev",
        expected_effective_connection={},
        expected_effective_vars={
            "shared": "cli",
            "env_only": "present",
            "local_only": "present",
            "cli_only": "present",
        },
    ),
    BuildCompileInputsTestCase(
        description="maps every supported project default into compile model config",
        repo_files=base_repo_files()
        | {
            "sqlbuild_project.yml": """
name: demo
adapter: duckdb

defaults:
  materialized: incremental
  database: analytics
  schema: marts
  incremental_strategy: merge
  incremental_mode: microbatch
  lookback: 1d
  batch_size: 1h
  query_change_backfill: bounded(30d)
  schema_change_backfill:
    add_column: bounded(7d)
    type_change: full
  row_diff_exclude_columns:
    - loaded_at
    - run_id
""".strip()
            + "\n",
            "models/staging/orders.sql": "MODEL ();\n\nselect 1\n",
        },
        selected_environment=None,
        cli_vars=None,
        run_id=None,
        expected_model_schema_names=(None,),
        expected_model_config_values=(
            {
                "materialized": "incremental",
                "database": "analytics",
                "schema": "marts",
                "incremental_strategy": "merge",
                "incremental_mode": "microbatch",
                "lookback": "1d",
                "batch_size": "1h",
                "query_change_backfill": "bounded(30d)",
                "schema_change_backfill": {
                    "add_column": "bounded(7d)",
                    "type_change": "full",
                },
                "row_diff_exclude_columns": ("loaded_at", "run_id"),
            },
        ),
        expected_model_query_sqls=("select 1",),
        expected_model_path_defaults=(None,),
        expected_seed_names=(),
        expected_source_names=(),
        expected_effective_environment_name=None,
        expected_effective_connection={},
        expected_effective_vars={},
    ),
    BuildCompileInputsTestCase(
        description="expands vars env connection model config and environment overrides",
        repo_files=base_repo_files()
        | {
            "sqlbuild_project.yml": """
name: demo
adapter: duckdb
default_environment: dev

connection:
  path: "/tmp/${user}.db"
  warehouse: "${schema_prefix}_wh"

vars:
  user: "${ENV:USER}"
  schema_prefix: "analytics_${user}"

defaults:
  database: "${schema_prefix}"
  schema: marts
  query_change_backfill: "${ENV:BACKFILL_POLICY}"
  row_diff_exclude_columns:
    - "${schema_prefix}_loaded_at"

environments:
  dev:
    database: "dev_${CTX:model.database}"
    schema: "dev_${ENV:USER}_${CTX:model.schema}"
""".strip()
            + "\n",
            "models/staging/orders.sql": """
MODEL (
  alias: "${CTX:model.name}_${CTX:run.environment}",
  config:
    cluster_by: ["${schema_prefix}_day"]
    run_label: "${CTX:run.id}"
    logical_alias: "${CTX:model.alias}"
    target_table: "${CTX:target.table}"
    target_schema: "${CTX:target.schema}"
    target_database: "${CTX:target.database}"
    target_qualified: "${CTX:target.qualified}"
);

select 1
""".strip()
            + "\n",
        },
        selected_environment=None,
        cli_vars=None,
        run_id="run_123",
        expected_model_schema_names=(None,),
        expected_model_config_values=(
            {
                "database": "dev_analytics_kevin",
                "schema": "dev_kevin_marts",
                "query_change_backfill": "bounded(30d)",
                "row_diff_exclude_columns": ("analytics_kevin_loaded_at",),
                "alias": "orders_dev",
                "config": {
                    "cluster_by": ["analytics_kevin_day"],
                    "run_label": "run_123",
                    "logical_alias": "orders_dev",
                    "target_table": "orders_dev",
                    "target_schema": "dev_kevin_marts",
                    "target_database": "dev_analytics_kevin",
                    "target_qualified": "dev_analytics_kevin.dev_kevin_marts.orders_dev",
                },
            },
        ),
        expected_model_query_sqls=("select 1",),
        expected_model_path_defaults=(None,),
        expected_seed_names=(),
        expected_source_names=(),
        expected_effective_environment_name="dev",
        expected_effective_connection={
            "path": "/tmp/kevin.db",
            "warehouse": "analytics_kevin_wh",
        },
        expected_effective_vars={
            "user": "kevin",
            "schema_prefix": "analytics_kevin",
        },
        environment_variables={"USER": "kevin", "BACKFILL_POLICY": "bounded(30d)"},
    ),
    BuildCompileInputsTestCase(
        description="resolves run context before late target context",
        repo_files=base_repo_files()
        | {
            "sqlbuild_project.yml": """
name: demo
adapter: duckdb
default_environment: ci

environments:
  ci:
    database: "db_${CTX:run.environment}"
    schema: "schema_${CTX:run.id}"
""".strip()
            + "\n",
            "models/staging/orders.sql": """
MODEL (
  alias: "orders_${CTX:run.environment}",
  config:
    run_label: "${CTX:run.id}"
    target_qualified: "${CTX:target.qualified}"
);

select 1
""".strip()
            + "\n",
        },
        selected_environment=None,
        cli_vars=None,
        run_id="run_123",
        expected_model_schema_names=(None,),
        expected_model_config_values=(
            {
                "database": "db_ci",
                "schema": "schema_run_123",
                "alias": "orders_ci",
                "config": {
                    "run_label": "run_123",
                    "target_qualified": "db_ci.schema_run_123.orders_ci",
                },
            },
        ),
        expected_model_query_sqls=("select 1",),
        expected_model_path_defaults=(None,),
        expected_seed_names=(),
        expected_source_names=(),
        expected_effective_environment_name="ci",
        expected_effective_connection={},
        expected_effective_vars={},
    ),
    BuildCompileInputsTestCase(
        description="supports multi hop var expansion and preserve environment overrides",
        repo_files=base_repo_files()
        | {
            "sqlbuild_project.yml": """
name: demo
adapter: duckdb
default_environment: dev

vars:
  base: analytics
  stage_one: "${base}_team"
  stage_two: "${stage_one}_prod"

defaults:
  database: "${stage_two}"
  schema: marts

path_defaults:
  models/staging:
    alias: "${stage_two}_orders"

environments:
  dev:
    database: preserve
    schema: preserve
""".strip()
            + "\n",
            "models/staging/orders.sql": "MODEL ();\n\nselect 1\n",
        },
        selected_environment=None,
        cli_vars=None,
        run_id=None,
        expected_model_schema_names=(None,),
        expected_model_config_values=(
            {
                "database": "analytics_team_prod",
                "schema": "marts",
                "alias": "analytics_team_prod_orders",
            },
        ),
        expected_model_query_sqls=("select 1",),
        expected_model_path_defaults=("models/staging",),
        expected_seed_names=(),
        expected_source_names=(),
        expected_effective_environment_name="dev",
        expected_effective_connection={},
        expected_effective_vars={
            "base": "analytics",
            "stage_one": "analytics_team",
            "stage_two": "analytics_team_prod",
        },
    ),
    BuildCompileInputsTestCase(
        description="expands macros in model query and hook sql strings",
        repo_files=base_repo_files()
        | {
            "macros/common.py": """
def project_columns() -> str:
    return "order_id, customer_id"

def grant_target(target_name: str) -> str:
    return f"GRANT SELECT ON {target_name} TO analyst_role"
""".strip()
            + "\n",
            "sqlbuild_project.yml": """
name: demo
adapter: duckdb
default_environment: dev

defaults:
  schema: marts

environments:
  dev:
    database: analytics
""".strip()
            + "\n",
            "models/staging/orders.sql": """
MODEL (
  alias: orders_dev,
  post_hook: ["@grant_target('${CTX:target.qualified}')"]
);

select @project_columns() from raw_orders
""".strip()
            + "\n",
        },
        selected_environment=None,
        cli_vars=None,
        run_id="run_123",
        expected_model_schema_names=(None,),
        expected_model_config_values=(
            {
                "schema": "marts",
                "alias": "orders_dev",
                "database": "analytics",
                "post_hook": ["GRANT SELECT ON analytics.marts.orders_dev TO analyst_role"],
            },
        ),
        expected_model_path_defaults=(None,),
        expected_seed_names=(),
        expected_source_names=(),
        expected_effective_environment_name="dev",
        expected_effective_connection={},
        expected_effective_vars={},
        expected_model_query_sqls=("select order_id, customer_id from raw_orders",),
    ),
    BuildCompileInputsTestCase(
        description="generates clickstate style run ids when none are provided",
        repo_files=base_repo_files() | {"models/staging/orders.sql": "MODEL ();\n\nselect 1\n"},
        selected_environment=None,
        cli_vars=None,
        run_id=None,
        expected_model_schema_names=(None,),
        expected_model_config_values=({},),
        expected_model_query_sqls=("select 1",),
        expected_model_path_defaults=(None,),
        expected_seed_names=(),
        expected_source_names=(),
        expected_effective_environment_name=None,
        expected_effective_connection={},
        expected_effective_vars={},
    ),
]


@pytest.mark.parametrize(
    "test_case",
    TEST_CASES,
    ids=[case.description for case in TEST_CASES],
)
def test_given_discovered_inputs_when_building_compile_inputs_then_it_attaches_metadata(
    test_case: BuildCompileInputsTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment_name: str
    environment_value: str
    for environment_name, environment_value in test_case.environment_variables.items():
        monkeypatch.setenv(environment_name, environment_value)

    write_repo_files(tmp_path, test_case.repo_files)

    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(project_dir=tmp_path)
    compile_inputs: CompileProjectInputs = build_compile_inputs(
        discovered_inputs,
        selected_environment=test_case.selected_environment,
        cli_vars=test_case.cli_vars,
        run_id=test_case.run_id,
    )

    assert (
        tuple(
            None if model_input.schema_entry is None else model_input.schema_entry.name
            for model_input in compile_inputs.model_inputs
        )
        == test_case.expected_model_schema_names
    )
    assert (
        tuple(model_input.config.values for model_input in compile_inputs.model_inputs)
        == test_case.expected_model_config_values
    )
    assert (
        tuple(model_input.query_sql for model_input in compile_inputs.model_inputs)
        == test_case.expected_model_query_sqls
    )
    assert (
        tuple(
            model_input.config.matched_path_default for model_input in compile_inputs.model_inputs
        )
        == test_case.expected_model_path_defaults
    )
    assert (
        tuple(seed_input.schema_entry.name for seed_input in compile_inputs.seed_inputs)
        == test_case.expected_seed_names
    )
    assert (
        tuple(source_input.source_entry.name for source_input in compile_inputs.source_inputs)
        == test_case.expected_source_names
    )
    assert (
        compile_inputs.effective_environment_name == test_case.expected_effective_environment_name
    )
    assert compile_inputs.effective_connection == test_case.expected_effective_connection
    assert compile_inputs.effective_vars == test_case.expected_effective_vars
    assert (
        compile_inputs.run_id == test_case.run_id
        if test_case.run_id is not None
        else re.fullmatch(r"\d{8}T\d{6}Z_[0-9a-f]{6}", compile_inputs.run_id) is not None
    )


COMPILE_ERROR_TEST_CASES: list[BuildCompileInputsErrorTestCase] = [
    BuildCompileInputsErrorTestCase(
        description="raises when model config field contains a macro call",
        repo_files=base_repo_files()
        | {
            "macros/common.py": """
def dynamic_schema() -> str:
    return "marts"
""".strip()
            + "\n",
            "models/staging/orders.sql": """
MODEL (
  schema: "@dynamic_schema()",
);

select 1
""".strip()
            + "\n",
        },
        selected_environment=None,
        run_id=None,
        expected_error_fragment="model config field 'schema' does not allow macros",
    ),
    BuildCompileInputsErrorTestCase(
        description=(
            "raises when a schema model declaration is outside its effective directory scope"
        ),
        repo_files=base_repo_files()
        | {
            "models/staging/orders.sql": "MODEL ();\n\nselect 1\n",
            "models/marts/schema.yml": """
models:
  - name: orders
""".strip()
            + "\n",
        },
        selected_environment=None,
        run_id=None,
        expected_error_fragment="does not match any discovered model file in that directory scope",
    ),
    BuildCompileInputsErrorTestCase(
        description="raises when a seed csv exists without a matching schema declaration",
        repo_files=base_repo_files()
        | {
            "seeds/extra_seed.csv": "country_code\nUS\n",
        },
        selected_environment=None,
        run_id=None,
        expected_error_fragment="has no matching seed declaration in schema.yml",
    ),
    BuildCompileInputsErrorTestCase(
        description="raises when the selected environment does not exist",
        repo_files=base_repo_files() | {"models/staging/orders.sql": "MODEL ();\n\nselect 1\n"},
        selected_environment="missing",
        run_id=None,
        expected_error_fragment="Unknown environment 'missing'",
    ),
    BuildCompileInputsErrorTestCase(
        description="raises when the local environment does not exist",
        repo_files=base_repo_files()
        | {
            "sqlbuild_local.yml": """
environment: missing
""".strip()
            + "\n",
            "models/staging/orders.sql": "MODEL ();\n\nselect 1\n",
        },
        selected_environment=None,
        run_id=None,
        expected_error_fragment="Unknown environment 'missing'",
    ),
    BuildCompileInputsErrorTestCase(
        description="raises when the project default environment does not exist",
        repo_files=base_repo_files()
        | {
            "sqlbuild_project.yml": """
name: demo
adapter: duckdb
default_environment: missing
""".strip()
            + "\n",
            "models/staging/orders.sql": "MODEL ();\n\nselect 1\n",
        },
        selected_environment=None,
        run_id=None,
        expected_error_fragment="Unknown environment 'missing'",
    ),
    BuildCompileInputsErrorTestCase(
        description="raises when effective vars reference an unknown project variable",
        repo_files=base_repo_files()
        | {
            "sqlbuild_project.yml": """
name: demo
adapter: duckdb

vars:
  user: "${missing}"
""".strip()
            + "\n",
            "models/staging/orders.sql": "MODEL ();\n\nselect 1\n",
        },
        selected_environment=None,
        run_id=None,
        expected_error_fragment="effective vars references unknown variable 'missing'",
    ),
    BuildCompileInputsErrorTestCase(
        description="raises when connection templates reference missing env vars",
        repo_files=base_repo_files()
        | {
            "sqlbuild_project.yml": """
name: demo
adapter: duckdb

connection:
  path: "${ENV:SQLBUILD_DB_PATH}"
""".strip()
            + "\n",
            "models/staging/orders.sql": "MODEL ();\n\nselect 1\n",
        },
        selected_environment=None,
        run_id=None,
        expected_error_fragment=(
            "effective connection references missing ENV variable 'SQLBUILD_DB_PATH'"
        ),
    ),
    BuildCompileInputsErrorTestCase(
        description="raises when model config uses unknown ctx keys",
        repo_files=base_repo_files()
        | {
            "sqlbuild_project.yml": """
name: demo
adapter: duckdb
""".strip()
            + "\n",
            "models/staging/orders.sql": """
MODEL (
  schema: "${CTX:this}",
);

select 1
""".strip()
            + "\n",
        },
        selected_environment=None,
        run_id=None,
        expected_error_fragment="model config references unknown CTX key 'this'",
    ),
    BuildCompileInputsErrorTestCase(
        description="raises when environment override references an unknown ctx key",
        repo_files=base_repo_files()
        | {
            "sqlbuild_project.yml": """
name: demo
adapter: duckdb
default_environment: dev

defaults:
  schema: marts

environments:
  dev:
    schema: "dev_${CTX:target.missing}"
""".strip()
            + "\n",
            "models/staging/orders.sql": "MODEL ();\n\nselect 1\n",
        },
        selected_environment=None,
        run_id=None,
        expected_error_fragment="environment schema references unknown CTX key 'target.missing'",
    ),
    BuildCompileInputsErrorTestCase(
        description="raises when environment database override references unavailable ctx value",
        repo_files=base_repo_files()
        | {
            "sqlbuild_project.yml": """
name: demo
adapter: duckdb
default_environment: dev

environments:
  dev:
    database: "dev_${CTX:model.database}"
""".strip()
            + "\n",
            "models/staging/orders.sql": "MODEL ();\n\nselect 1\n",
        },
        selected_environment=None,
        run_id=None,
        expected_error_fragment=(
            "environment database references CTX key 'model.database' but no value is available"
        ),
    ),
    BuildCompileInputsErrorTestCase(
        description="raises when effective vars contain a cyclic reference",
        repo_files=base_repo_files()
        | {
            "sqlbuild_project.yml": """
name: demo
adapter: duckdb

vars:
  first: "${second}"
  second: "${first}"
""".strip()
            + "\n",
            "models/staging/orders.sql": "MODEL ();\n\nselect 1\n",
        },
        selected_environment=None,
        run_id=None,
        expected_error_fragment=(
            "effective vars contain a cyclic reference: first -> second -> first"
        ),
    ),
    BuildCompileInputsErrorTestCase(
        description="raises when templates use an unsupported namespace",
        repo_files=base_repo_files()
        | {
            "sqlbuild_project.yml": """
name: demo
adapter: duckdb

vars:
  user: kevin

defaults:
  schema: "${SQLBUILD:user}"
""".strip()
            + "\n",
            "models/staging/orders.sql": "MODEL ();\n\nselect 1\n",
        },
        selected_environment=None,
        run_id=None,
        expected_error_fragment="model config references unsupported template namespace 'SQLBUILD'",
    ),
    BuildCompileInputsErrorTestCase(
        description="raises when connection values use disallowed ctx templates",
        repo_files=base_repo_files()
        | {
            "sqlbuild_project.yml": """
name: demo
adapter: duckdb

connection:
  path: "${CTX:schema}"
""".strip()
            + "\n",
            "models/staging/orders.sql": "MODEL ();\n\nselect 1\n",
        },
        selected_environment=None,
        run_id=None,
        expected_error_fragment="effective connection does not allow CTX templates",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    COMPILE_ERROR_TEST_CASES,
    ids=[case.description for case in COMPILE_ERROR_TEST_CASES],
)
def test_given_attachment_conflicts_when_building_compile_inputs_then_it_raises_clear_errors(
    test_case: BuildCompileInputsErrorTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment_name: str
    environment_value: str
    for environment_name, environment_value in test_case.environment_variables.items():
        monkeypatch.setenv(environment_name, environment_value)

    write_repo_files(tmp_path, test_case.repo_files)

    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(project_dir=tmp_path)

    with pytest.raises(ValueError, match=test_case.expected_error_fragment):
        build_compile_inputs(
            discovered_inputs,
            selected_environment=test_case.selected_environment,
            run_id=test_case.run_id,
        )
