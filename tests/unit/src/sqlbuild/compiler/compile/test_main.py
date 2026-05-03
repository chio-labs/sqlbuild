from __future__ import annotations

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
        expected_model_schema_names=(None, "orders"),
        expected_model_config_values=(
            {"materialized": "incremental", "schema": "nested", "batch_size": "30m"},
            {"materialized": "view", "schema": "staging", "batch_size": "1h"},
        ),
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
        expected_model_schema_names=(None,),
        expected_model_config_values=({},),
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
        expected_model_schema_names=(None,),
        expected_model_config_values=({},),
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
        expected_model_schema_names=(None,),
        expected_model_config_values=({},),
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
        expected_model_schema_names=(None,),
        expected_model_config_values=({},),
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
        expected_model_schema_names=(None,),
        expected_model_config_values=({},),
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
        expected_model_schema_names=(None,),
        expected_model_config_values=({},),
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
        expected_model_schema_names=(None,),
        expected_model_config_values=({},),
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
        expected_model_schema_names=(None,),
        expected_model_config_values=({},),
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
) -> None:
    write_repo_files(tmp_path, test_case.repo_files)

    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(project_dir=tmp_path)
    compile_inputs: CompileProjectInputs = build_compile_inputs(
        discovered_inputs,
        selected_environment=test_case.selected_environment,
        cli_vars=test_case.cli_vars,
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


COMPILE_ERROR_TEST_CASES: list[BuildCompileInputsErrorTestCase] = [
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
        expected_error_fragment="does not match any discovered model file in that directory scope",
    ),
    BuildCompileInputsErrorTestCase(
        description="raises when a seed csv exists without a matching schema declaration",
        repo_files=base_repo_files()
        | {
            "seeds/extra_seed.csv": "country_code\nUS\n",
        },
        selected_environment=None,
        expected_error_fragment="has no matching seed declaration in schema.yml",
    ),
    BuildCompileInputsErrorTestCase(
        description="raises when the selected environment does not exist",
        repo_files=base_repo_files() | {"models/staging/orders.sql": "MODEL ();\n\nselect 1\n"},
        selected_environment="missing",
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
        expected_error_fragment="Unknown environment 'missing'",
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
) -> None:
    write_repo_files(tmp_path, test_case.repo_files)

    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(project_dir=tmp_path)

    with pytest.raises(ValueError, match=test_case.expected_error_fragment):
        build_compile_inputs(
            discovered_inputs,
            selected_environment=test_case.selected_environment,
        )
