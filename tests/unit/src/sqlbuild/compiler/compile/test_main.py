from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

import pytest

from sqlbuild.compiler.compile.main.build_compile_inputs import build_compile_inputs
from sqlbuild.compiler.compile.models import CompileProjectInputs
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from tests.unit.src.sqlbuild.compiler.compile._test_helpers import (
    base_repo_files,
)
from tests.unit.src.sqlbuild.compiler.compile._test_types import (
    BuildCompileInputsErrorTestCase,
    BuildCompileInputsTestCase,
    SeedRefRegressionTestCase,
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
  staging:
    materialized: view
    schema: staging
  staging/nested:
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
connection:
  path: local.db
settings:
  sqlglot: false
  sql_validation: false
  max_concurrency: 4
vars:
  shared: local
  local_only: present
""".strip()
            + "\n",
            "models/staging/orders.sql": "MODEL ();\n\nselect 1\n",
            "models/staging/nested/orders_enriched.sql": """
MODEL (
  materialized incremental,
  incremental_strategy delete_insert,
  cursor event_time,
  cursor_type timestamp,
  cursor_grain second,
  incremental_mode microbatch,
  batch_size 30m,
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
            {
                "materialized": "incremental",
                "schema": "nested",
                "incremental_strategy": "delete_insert",
                "cursor": "event_time",
                "cursor_type": "timestamp",
                "cursor_grain": "second",
                "incremental_mode": "microbatch",
                "batch_size": "30m",
            },
            {"materialized": "view", "schema": "staging", "batch_size": "1h"},
        ),
        expected_model_query_sqls=("select 1", "select 1"),
        expected_model_path_defaults=("staging/nested", "staging"),
        expected_seed_names=("country_codes",),
        expected_source_names=("raw_orders",),
        expected_effective_environment_name="dev",
        expected_effective_connection={"path": "local.db", "warehouse": "dev_wh"},
        expected_effective_vars={
            "shared": "cli",
            "project_only": "present",
            "env_only": "present",
            "local_only": "present",
            "cli_only": "present",
        },
        expected_effective_sqlglot=False,
        expected_effective_sql_validation=False,
        expected_effective_max_concurrency=4,
        expected_model_references=((), ()),
        expected_audit_references=(),
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
        expected_model_references=((),),
        expected_audit_references=(),
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
        expected_model_references=((),),
        expected_audit_references=(),
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
        expected_model_references=((),),
        expected_audit_references=(),
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
        expected_model_references=((),),
        expected_audit_references=(),
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
        expected_model_references=((),),
        expected_audit_references=(),
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
        expected_model_references=((),),
        expected_audit_references=(),
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
        expected_model_references=((),),
        expected_audit_references=(),
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
        expected_model_references=((),),
        expected_audit_references=(),
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
  query_change_backfill: bounded-30d
  schema_change_backfill:
    add_column: bounded-7d
    type_change: full
  row_diff_exclude_columns:
    - loaded_at
    - run_id
  row_diff_tolerances:
    by_column:
      revenue:
        absolute: 0.01
""".strip()
            + "\n",
            "models/staging/orders.sql": (
                "MODEL (\n  unique_key [order_id],"
                "\n  cursor event_time,"
                "\n  cursor_type timestamp,"
                "\n  cursor_grain second,"
                "\n);\n\nselect 1\n"
            ),
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
                "unique_key": ["order_id"],
                "cursor": "event_time",
                "cursor_type": "timestamp",
                "cursor_grain": "second",
                "lookback": "1d",
                "batch_size": "1h",
                "query_change_backfill": "bounded-30d",
                "schema_change_backfill": {
                    "add_column": "bounded-7d",
                    "type_change": "full",
                },
                "row_diff_exclude_columns": ("loaded_at", "run_id"),
                "row_diff_tolerances": {
                    "by_column": {"revenue": {"absolute": 0.01}},
                },
            },
        ),
        expected_model_query_sqls=("select 1",),
        expected_model_path_defaults=(None,),
        expected_seed_names=(),
        expected_source_names=(),
        expected_effective_environment_name=None,
        expected_effective_connection={},
        expected_effective_vars={},
        expected_model_references=((),),
        expected_audit_references=(),
    ),
    BuildCompileInputsTestCase(
        description="maps append cursor inclusive from project defaults",
        repo_files=base_repo_files()
        | {
            "sqlbuild_project.yml": """
name: demo
adapter: duckdb

defaults:
  materialized: incremental
  incremental_strategy: append
  append_cursor_inclusive: false
""".strip()
            + "\n",
            "models/staging/orders.sql": (
                "MODEL (\n  cursor event_time,"
                "\n  cursor_type timestamp,"
                "\n  cursor_grain second,"
                "\n);\n\nselect 1\n"
            ),
        },
        selected_environment=None,
        cli_vars=None,
        run_id=None,
        expected_model_schema_names=(None,),
        expected_model_config_values=(
            {
                "materialized": "incremental",
                "incremental_strategy": "append",
                "append_cursor_inclusive": False,
                "cursor": "event_time",
                "cursor_type": "timestamp",
                "cursor_grain": "second",
            },
        ),
        expected_model_query_sqls=("select 1",),
        expected_model_path_defaults=(None,),
        expected_seed_names=(),
        expected_source_names=(),
        expected_effective_environment_name=None,
        expected_effective_connection={},
        expected_effective_vars={},
        expected_model_references=((),),
        expected_audit_references=(),
    ),
    BuildCompileInputsTestCase(
        description="merges row diff config from project defaults and model header",
        repo_files=base_repo_files()
        | {
            "sqlbuild_project.yml": """
name: demo
adapter: duckdb

defaults:
  row_diff_exclude_columns:
    - loaded_at
  row_diff_tolerances:
    by_type:
      float:
        relative: 0.0001
      integer:
        absolute: 1
    by_column:
      revenue:
        absolute: 0.01
""".strip()
            + "\n",
            "models/staging/orders.sql": """
MODEL (
  row_diff_exclude_columns [run_id, loaded_at],
  row_diff_tolerances (
    by_type (
      float (
        relative 0.00001,
      ),
    ),
    by_column (
      conversion_rate (
        relative 0.001,
        absolute 0.0001,
      ),
    ),
  ),
);

select 1
""".strip()
            + "\n",
        },
        selected_environment=None,
        cli_vars=None,
        run_id=None,
        expected_model_schema_names=(None,),
        expected_model_config_values=(
            {
                "row_diff_exclude_columns": ("loaded_at", "run_id"),
                "row_diff_tolerances": {
                    "by_type": {
                        "float": {"relative": 0.00001},
                        "integer": {"absolute": 1},
                    },
                    "by_column": {
                        "revenue": {"absolute": 0.01},
                        "conversion_rate": {
                            "relative": 0.001,
                            "absolute": 0.0001,
                        },
                    },
                },
            },
        ),
        expected_model_query_sqls=("select 1",),
        expected_model_path_defaults=(None,),
        expected_seed_names=(),
        expected_source_names=(),
        expected_effective_environment_name=None,
        expected_effective_connection={},
        expected_effective_vars={},
        expected_model_references=((),),
        expected_audit_references=(),
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
  alias '${CTX:model.name}_${CTX:run.environment}',
  config (
    cluster_by ['${schema_prefix}_day'],
    run_label '${CTX:run.id}',
    logical_alias '${CTX:model.alias}',
    target_table '${CTX:target.table}',
    target_schema '${CTX:target.schema}',
    target_database '${CTX:target.database}',
    target_qualified '${CTX:target.qualified}',
  ),
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
                "query_change_backfill": "bounded-30d",
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
        environment_variables={"USER": "kevin", "BACKFILL_POLICY": "bounded-30d"},
        expected_model_references=((),),
        expected_audit_references=(),
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
  alias 'orders_${CTX:run.environment}',
  config (
    run_label '${CTX:run.id}',
    target_qualified '${CTX:target.qualified}',
  ),
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
        expected_model_references=((),),
        expected_audit_references=(),
    ),
    BuildCompileInputsTestCase(
        description="expands helper functions in config interpolation",
        repo_files=base_repo_files()
        | {
            "sqlbuild_project.yml": """
name: demo
adapter: duckdb

defaults:
  materialized: incremental
  incremental_strategy: append
  database: "${if(ENV:CI, 'ci_db', 'dev_db')}"
  schema: "${coalesce(ENV:CUSTOM_SCHEMA, 'fallback_schema')}"
  append_cursor_inclusive: "${if(eq(ENV:APPEND_INCLUSIVE, '0'), false, true)}"
""".strip()
            + "\n",
            "models/staging/orders.sql": """
MODEL (
  cursor event_time,
  cursor_type timestamp,
  cursor_grain second,
  alias '${if(eq(CTX:run.id, "run_123"), "orders_dev", "orders_prod")}',
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
                "materialized": "incremental",
                "incremental_strategy": "append",
                "database": "ci_db",
                "schema": "fallback_schema",
                "append_cursor_inclusive": False,
                "cursor": "event_time",
                "cursor_type": "timestamp",
                "cursor_grain": "second",
                "alias": "orders_dev",
            },
        ),
        expected_model_query_sqls=("select 1",),
        expected_model_path_defaults=(None,),
        expected_seed_names=(),
        expected_source_names=(),
        expected_effective_environment_name=None,
        expected_effective_connection={},
        expected_effective_vars={},
        environment_variables={"CI": "1", "APPEND_INCLUSIVE": "0"},
        expected_model_references=((),),
        expected_audit_references=(),
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
  staging:
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
        expected_model_path_defaults=("staging",),
        expected_seed_names=(),
        expected_source_names=(),
        expected_effective_environment_name="dev",
        expected_effective_connection={},
        expected_effective_vars={
            "base": "analytics",
            "stage_one": "analytics_team",
            "stage_two": "analytics_team_prod",
        },
        expected_model_references=((),),
        expected_audit_references=(),
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

settings:
  default_audit_severity: warn

defaults:
  schema: marts

environments:
  dev:
    database: analytics
""".strip()
            + "\n",
            "models/staging/orders.sql": """
MODEL (
  alias orders_dev,
  post_hook ['@grant_target(\\'${CTX:target.qualified}\\')'],
);

select @project_columns() from __source("raw_orders")
""".strip()
            + "\n",
            "tests/unit/orders.sql": """
TEST ();

WITH
__source__raw_orders AS (
  SELECT @project_columns() FROM raw_orders
),
__expected__orders AS (
  SELECT @project_columns()
)
SELECT 1
""".strip()
            + "\n",
            "audits/orders.sql": """
AUDIT ();

SELECT @project_columns() FROM __source("raw_orders")
""".strip()
            + "\n",
            "sources/raw.yml": """
sources:
  - name: raw_orders
    table: orders
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
        expected_source_names=("raw_orders",),
        expected_test_sql_bodies=(
            """
WITH
__source__raw_orders AS (
  SELECT order_id, customer_id FROM raw_orders
),
__expected__orders AS (
  SELECT order_id, customer_id
)
SELECT 1
""".strip(),
        ),
        expected_test_authored_cte_names=(("__source__raw_orders",),),
        expected_test_mock_model_names=((),),
        expected_test_mock_source_names=(("raw_orders",),),
        expected_test_expected_model_names=(("orders",),),
        expected_audit_sql_bodies=('SELECT order_id, customer_id FROM __source("raw_orders")',),
        expected_effective_environment_name="dev",
        expected_effective_connection={},
        expected_effective_vars={},
        expected_model_query_sqls=('select order_id, customer_id from __source("raw_orders")',),
        expected_model_references=((("source", "raw_orders"),),),
        expected_audit_references=((("source", "raw_orders"),),),
    ),
    BuildCompileInputsTestCase(
        description="expands macros across multi block tests and audits",
        repo_files=base_repo_files()
        | {
            "macros/common.py": """
def project_columns() -> str:
    return "order_id"
""".strip()
            + "\n",
            "models/staging/orders.sql": "MODEL ();\n\nselect 1\n",
            "tests/unit/orders.sql": """
TEST (name: "first");

WITH
__ref__orders AS (
  SELECT @project_columns() FROM raw_orders
),
__expected__orders AS (
  SELECT @project_columns()
)
SELECT 1;

TEST (name: "second");

WITH
__ref__orders AS (
  SELECT @project_columns() FROM raw_customers
),
__expected__orders AS (
  SELECT @project_columns()
)
SELECT 1
""".strip()
            + "\n",
            "audits/orders.sql": """
AUDIT (name: "first");

SELECT @project_columns() FROM raw_orders;

AUDIT (name: "second");

SELECT @project_columns() FROM raw_customers
""".strip()
            + "\n",
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
        expected_effective_environment_name=None,
        expected_effective_connection={},
        expected_effective_vars={},
        expected_test_sql_bodies=(
            """
WITH
__ref__orders AS (
  SELECT order_id FROM raw_orders
),
__expected__orders AS (
  SELECT order_id
)
SELECT 1;
""".strip(),
            """
WITH
__ref__orders AS (
  SELECT order_id FROM raw_customers
),
__expected__orders AS (
  SELECT order_id
)
SELECT 1
""".strip(),
        ),
        expected_test_authored_cte_names=(
            ("__ref__orders",),
            ("__ref__orders",),
        ),
        expected_test_mock_model_names=(("orders",), ("orders",)),
        expected_test_mock_source_names=((), ()),
        expected_test_expected_model_names=(("orders",), ("orders",)),
        expected_audit_sql_bodies=(
            "SELECT order_id FROM raw_orders;",
            "SELECT order_id FROM raw_customers",
        ),
        expected_model_references=((),),
        expected_audit_references=((), ()),
    ),
    BuildCompileInputsTestCase(
        description="renders attached model and source audits from generic definitions",
        repo_files=base_repo_files()
        | {
            "models/marts/orders.sql": "MODEL ();\n\nselect 1\n",
            "models/marts/schema.yml": """
models:
  - name: orders
    audits:
      - model_not_null
    columns:
      - name: order_id
        audits:
          - column_not_null
""".strip()
            + "\n",
            "sources/raw.yml": """
sources:
  - name: raw_orders
    audits:
      - source_not_null
    columns:
      - name: order_id
        audits:
          - source_column_not_null
""".strip()
            + "\n",
            "audits/generic/model_not_null.sql": """
AUDIT ();

SELECT 1 FROM __ref("@model")
""".strip()
            + "\n",
            "audits/generic/column_not_null.sql": """
AUDIT ();

SELECT @column FROM __ref("@model") WHERE @column IS NULL
""".strip()
            + "\n",
            "audits/generic/source_not_null.sql": """
AUDIT ();

SELECT 1 FROM __source("@source")
""".strip()
            + "\n",
            "audits/generic/source_column_not_null.sql": """
AUDIT ();

SELECT @column FROM __source("@source") WHERE @column IS NULL
""".strip()
            + "\n",
        },
        selected_environment=None,
        cli_vars=None,
        run_id=None,
        expected_model_schema_names=("orders",),
        expected_model_config_values=({},),
        expected_model_query_sqls=("select 1",),
        expected_model_path_defaults=(None,),
        expected_seed_names=(),
        expected_source_names=("raw_orders",),
        expected_test_sql_bodies=(),
        expected_audit_sql_bodies=(
            'SELECT 1 FROM __ref("orders")',
            'SELECT order_id FROM __ref("orders") WHERE order_id IS NULL',
            'SELECT 1 FROM __source("raw_orders")',
            'SELECT order_id FROM __source("raw_orders") WHERE order_id IS NULL',
        ),
        expected_effective_environment_name=None,
        expected_effective_connection={},
        expected_effective_vars={},
        expected_model_references=((),),
        expected_audit_references=(
            (("ref", "orders"),),
            (("ref", "orders"),),
            (("source", "raw_orders"),),
            (("source", "raw_orders"),),
        ),
    ),
    BuildCompileInputsTestCase(
        description="skips generic audit definitions as direct executable audits",
        repo_files=base_repo_files()
        | {
            "models/marts/orders.sql": "MODEL ();\n\nselect 1\n",
            "audits/generic/not_null.sql": """
AUDIT ();

SELECT 1
""".strip()
            + "\n",
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
        expected_test_sql_bodies=(),
        expected_audit_sql_bodies=(),
        expected_effective_environment_name=None,
        expected_effective_connection={},
        expected_effective_vars={},
        expected_model_references=((),),
        expected_audit_references=(),
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
        expected_model_references=((),),
        expected_audit_references=(),
    ),
    BuildCompileInputsTestCase(
        description="allows invalid sql when project sql validation is disabled",
        repo_files=base_repo_files()
        | {
            "sqlbuild_project.yml": """
name: demo
adapter: duckdb

settings:
  sql_validation: false
""".strip()
            + "\n",
            "models/staging/broken.sql": "MODEL ();\n\nSELEC id FROM (SELECT 1\n",
        },
        selected_environment=None,
        cli_vars=None,
        run_id="test_run",
        expected_model_schema_names=(None,),
        expected_model_config_values=({},),
        expected_model_query_sqls=("SELEC id FROM (SELECT 1",),
        expected_model_path_defaults=(None,),
        expected_seed_names=(),
        expected_source_names=(),
        expected_effective_environment_name=None,
        expected_effective_connection={},
        expected_effective_vars={},
        expected_effective_sql_validation=False,
        expected_model_references=((),),
        expected_audit_references=(),
    ),
    BuildCompileInputsTestCase(
        description="allows invalid sql when no_sql_validation flag is set",
        repo_files=base_repo_files()
        | {
            "models/staging/broken.sql": "MODEL ();\n\nSELEC id FROM (SELECT 1\n",
        },
        selected_environment=None,
        cli_vars=None,
        run_id="test_run",
        no_sql_validation=True,
        expected_model_schema_names=(None,),
        expected_model_config_values=({},),
        expected_model_query_sqls=("SELEC id FROM (SELECT 1",),
        expected_model_path_defaults=(None,),
        expected_seed_names=(),
        expected_source_names=(),
        expected_effective_environment_name=None,
        expected_effective_connection={},
        expected_effective_vars={},
        expected_model_references=((),),
        expected_audit_references=(),
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
    write_repo_files: Callable[[Path, dict[str, str]], None],
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
        no_sql_validation=test_case.no_sql_validation,
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
        tuple(test_input.sql_body for test_input in compile_inputs.test_inputs)
        == test_case.expected_test_sql_bodies
    )
    assert (
        tuple(
            tuple(cte.name for cte in test_input.authored_ctes)
            for test_input in compile_inputs.test_inputs
        )
        == test_case.expected_test_authored_cte_names
    )
    assert (
        tuple(test_input.mock_model_names for test_input in compile_inputs.test_inputs)
        == test_case.expected_test_mock_model_names
    )
    assert (
        tuple(test_input.mock_source_names for test_input in compile_inputs.test_inputs)
        == test_case.expected_test_mock_source_names
    )
    assert (
        tuple(test_input.expected_model_names for test_input in compile_inputs.test_inputs)
        == test_case.expected_test_expected_model_names
    )
    assert (
        tuple(audit_input.sql_body for audit_input in compile_inputs.audit_inputs)
        == test_case.expected_audit_sql_bodies
    )
    assert (
        tuple(
            tuple((reference.ref_kind, reference.ref_name) for reference in model_input.references)
            for model_input in compile_inputs.model_inputs
        )
        == test_case.expected_model_references
    )
    assert (
        tuple(
            tuple((reference.ref_kind, reference.ref_name) for reference in audit_input.references)
            for audit_input in compile_inputs.audit_inputs
        )
        == test_case.expected_audit_references
    )
    assert (
        compile_inputs.effective_environment_name == test_case.expected_effective_environment_name
    )
    assert compile_inputs.effective_connection == test_case.expected_effective_connection
    assert compile_inputs.effective_settings.sqlglot is test_case.expected_effective_sqlglot
    assert (
        compile_inputs.effective_settings.sql_validation
        is test_case.expected_effective_sql_validation
    )
    assert (
        compile_inputs.effective_settings.max_concurrency
        == test_case.expected_effective_max_concurrency
    )
    assert compile_inputs.effective_vars == test_case.expected_effective_vars
    assert (
        compile_inputs.run_id == test_case.run_id
        if test_case.run_id is not None
        else re.fullmatch(r"\d{8}T\d{6}Z_[0-9a-f]{6}", compile_inputs.run_id) is not None
    )


COMPILE_ERROR_TEST_CASES: list[BuildCompileInputsErrorTestCase] = [
    BuildCompileInputsErrorTestCase(
        description="raises when a model references an unknown source",
        repo_files=base_repo_files()
        | {
            "models/staging/orders.sql": """
MODEL ();

SELECT * FROM __source("missing_source")
""".strip()
            + "\n",
        },
        selected_environment=None,
        run_id=None,
        expected_error_fragment="references unknown source 'missing_source'",
    ),
    BuildCompileInputsErrorTestCase(
        description="raises when an audit references an unknown source",
        repo_files=base_repo_files()
        | {
            "audits/orders.sql": """
AUDIT ();

SELECT * FROM __source("missing_source")
""".strip()
            + "\n",
        },
        selected_environment=None,
        run_id=None,
        expected_error_fragment="references unknown source 'missing_source'",
    ),
    BuildCompileInputsErrorTestCase(
        description="raises when an audit uses dbt refs",
        repo_files=base_repo_files()
        | {
            "audits/orders.sql": """
AUDIT ();

SELECT * FROM __dbt_ref("stg_orders")
""".strip()
            + "\n",
        },
        selected_environment=None,
        run_id=None,
        expected_error_fragment=(
            r"Audit file audits/orders\.sql may not use __dbt_ref\('stg_orders'\) right now"
        ),
    ),
    BuildCompileInputsErrorTestCase(
        description="raises when an attached source audit overrides implicit source context",
        repo_files=base_repo_files()
        | {
            "sources/raw.yml": """
sources:
  - name: raw_orders
    audits:
      - source_not_null:
          source: other_source
""".strip()
            + "\n",
            "audits/generic/source_not_null.sql": """
AUDIT ();

SELECT 1 FROM __source("@source")
""".strip()
            + "\n",
        },
        selected_environment=None,
        run_id=None,
        expected_error_fragment="must not override implicit source from attached context",
    ),
    BuildCompileInputsErrorTestCase(
        description="raises when an attached source audit references an unknown generic definition",
        repo_files=base_repo_files()
        | {
            "sources/raw.yml": """
sources:
  - name: raw_orders
    audits:
      - missing_definition
""".strip()
            + "\n",
        },
        selected_environment=None,
        run_id=None,
        expected_error_fragment="references unknown generic audit 'missing_definition'",
    ),
    BuildCompileInputsErrorTestCase(
        description="raises when a compiled test body references an unknown macro",
        repo_files=base_repo_files()
        | {
            "tests/unit/orders.sql": """
TEST ();

SELECT @missing_macro()
""".strip()
            + "\n",
        },
        selected_environment=None,
        run_id=None,
        expected_error_fragment="Unknown macro '@missing_macro'",
    ),
    BuildCompileInputsErrorTestCase(
        description="raises when a compiled test body lacks top level test ctes",
        repo_files=base_repo_files()
        | {
            "models/staging/orders.sql": "MODEL ();\n\nselect 1\n",
            "tests/unit/orders.sql": """
TEST ();

SELECT 1
""".strip()
            + "\n",
        },
        selected_environment=None,
        run_id=None,
        expected_error_fragment="must declare mock CTEs and one __expected__<model>",
    ),
    BuildCompileInputsErrorTestCase(
        description="raises when a compiled test body lacks ceremonial select one",
        repo_files=base_repo_files()
        | {
            "models/staging/orders.sql": "MODEL ();\n\nselect 1\n",
            "sources/raw.yml": """
sources:
  - name: raw_orders
""".strip()
            + "\n",
            "tests/unit/orders.sql": """
TEST ();

WITH
__source__raw_orders AS (
  SELECT 1 AS order_id
),
__expected__orders AS (
  SELECT 1 AS order_id
)
SELECT order_id FROM __expected__orders
""".strip()
            + "\n",
        },
        selected_environment=None,
        run_id=None,
        expected_error_fragment="must end with a ceremonial top-level `SELECT 1`",
    ),
    BuildCompileInputsErrorTestCase(
        description="raises when a compiled test body references an unknown source mock",
        repo_files=base_repo_files()
        | {
            "models/staging/orders.sql": "MODEL ();\n\nselect 1\n",
            "tests/unit/orders.sql": """
TEST ();

WITH
__source__missing_source AS (
  SELECT 1 AS order_id
),
__expected__orders AS (
  SELECT 1 AS order_id
)
SELECT 1
""".strip()
            + "\n",
        },
        selected_environment=None,
        run_id=None,
        expected_error_fragment="mocks unknown source 'missing_source'",
    ),
    BuildCompileInputsErrorTestCase(
        description="raises when a compiled test body references an unknown macro mock",
        repo_files=base_repo_files()
        | {
            "models/staging/orders.sql": "MODEL ();\n\nselect 1\n",
            "sources/raw.yml": """
sources:
  - name: raw_orders
""".strip()
            + "\n",
            "tests/unit/orders.sql": """
TEST ();

WITH
__macro__missing_macro AS (
  SELECT '1'
),
__source__raw_orders AS (
  SELECT 1 AS order_id
),
__expected__orders AS (
  SELECT 1 AS order_id
)
SELECT 1
""".strip()
            + "\n",
        },
        selected_environment=None,
        run_id=None,
        expected_error_fragment="mocks unknown macro 'missing_macro'",
    ),
    BuildCompileInputsErrorTestCase(
        description="raises when a compiled test body references an unknown expected model",
        repo_files=base_repo_files()
        | {
            "sources/raw.yml": """
sources:
  - name: raw_orders
""".strip()
            + "\n",
            "tests/unit/orders.sql": """
TEST ();

WITH
__source__raw_orders AS (
  SELECT 1 AS order_id
),
__expected__missing_model AS (
  SELECT 1 AS order_id
)
SELECT 1
""".strip()
            + "\n",
        },
        selected_environment=None,
        run_id=None,
        expected_error_fragment="expects unknown model 'missing_model'",
    ),
    BuildCompileInputsErrorTestCase(
        description="raises when a compiled test body uses a reserved helper cte name",
        repo_files=base_repo_files()
        | {
            "models/staging/orders.sql": "MODEL ();\n\nselect 1\n",
            "sources/raw.yml": """
sources:
  - name: raw_orders
""".strip()
            + "\n",
            "tests/unit/orders.sql": """
TEST ();

WITH
__actual AS (
  SELECT 1 AS order_id
),
__source__raw_orders AS (
  SELECT * FROM __actual
),
__expected__orders AS (
  SELECT 1 AS order_id
)
SELECT 1
""".strip()
            + "\n",
        },
        selected_environment=None,
        run_id=None,
        expected_error_fragment="uses reserved helper CTE name '__actual'",
    ),
    BuildCompileInputsErrorTestCase(
        description="raises when a compiled audit body references an unknown macro",
        repo_files=base_repo_files()
        | {
            "audits/orders.sql": """
AUDIT ();

SELECT @missing_macro()
""".strip()
            + "\n",
        },
        selected_environment=None,
        run_id=None,
        expected_error_fragment="Unknown macro '@missing_macro'",
    ),
    BuildCompileInputsErrorTestCase(
        description="raises when macro files collide during compile",
        repo_files=base_repo_files()
        | {
            "macros/common.py": """
def project_columns() -> str:
    return "order_id"
""".strip()
            + "\n",
            "macros/nested/common.py": """
def project_columns() -> str:
    return "customer_id"
""".strip()
            + "\n",
            "models/staging/orders.sql": "MODEL ();\n\nselect 1\n",
        },
        selected_environment=None,
        run_id=None,
        expected_error_fragment="Macro name collision for 'project_columns'",
    ),
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
  schema '@dynamic_schema()',
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
  schema '${CTX:this}',
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
    BuildCompileInputsErrorTestCase(
        description="raises when model query sql has invalid syntax",
        repo_files=base_repo_files()
        | {
            "models/staging/broken.sql": "MODEL ();\n\nSELEC id FROM (SELECT 1\n",
        },
        selected_environment=None,
        run_id=None,
        expected_error_fragment="SQL syntax error in model 'broken'",
    ),
    BuildCompileInputsErrorTestCase(
        description="raises when pre_hook sql has invalid syntax",
        repo_files=base_repo_files()
        | {
            "models/staging/broken.sql": (
                "MODEL (pre_hook 'THIS IS NOT VALID SQL');\n\nSELECT 1 AS id\n"
            ),
        },
        selected_environment=None,
        run_id=None,
        expected_error_fragment="SQL syntax error in pre_hook for model 'broken'",
    ),
    BuildCompileInputsErrorTestCase(
        description="raises when post_hook sql has invalid syntax",
        repo_files=base_repo_files()
        | {
            "models/staging/broken.sql": (
                "MODEL (post_hook 'THIS IS NOT VALID SQL');\n\nSELECT 1 AS id\n"
            ),
        },
        selected_environment=None,
        run_id=None,
        expected_error_fragment="SQL syntax error in post_hook for model 'broken'",
    ),
    BuildCompileInputsErrorTestCase(
        description="raises when model header tags is a string instead of list",
        repo_files=base_repo_files()
        | {
            "models/staging/orders.sql": "MODEL (tags nightly);\n\nSELECT 1\n",
        },
        selected_environment=None,
        run_id=None,
        expected_error_fragment="tags must be a list",
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
    write_repo_files: Callable[[Path, dict[str, str]], None],
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


@pytest.mark.parametrize(
    "test_case",
    [
        SeedRefRegressionTestCase(
            description="model referencing a seed via __ref does not raise unknown model error",
            repo_files=base_repo_files()
            | {
                "seeds/waffle_types.csv": "waffle_type_id,waffle_name\n1,Classic\n",
                "seeds/schema.yml": (
                    "seeds:\n"
                    "  - name: waffle_types\n"
                    "    columns:\n"
                    "      - name: waffle_type_id\n"
                    "        type: INTEGER\n"
                    "      - name: waffle_name\n"
                    "        type: VARCHAR\n"
                ),
                "models/orders.sql": (
                    'MODEL ();\n\nSELECT waffle_type_id FROM __ref("waffle_types")'
                ),
            },
            expected_model_count=1,
        ),
    ],
    ids=["model referencing a seed via __ref does not raise unknown model error"],
)
def test_given_model_referencing_seed_when_building_compile_inputs_then_succeeds(
    test_case: SeedRefRegressionTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(tmp_path, test_case.repo_files)

    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(project_dir=tmp_path)
    compile_inputs: CompileProjectInputs = build_compile_inputs(discovered_inputs)

    assert len(compile_inputs.model_inputs) == test_case.expected_model_count
