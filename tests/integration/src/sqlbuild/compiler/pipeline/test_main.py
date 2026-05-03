from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest

from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.compiler.planner.models import ModelPlanEntry
from sqlbuild.integrations.duckdb.client import DuckDbAdapter
from tests.integration.src.sqlbuild.compiler.pipeline._test_types import (
    DeferToIntegrationTestCase,
    ExpectedModelEntry,
    RunCompilePipelineIntegrationTestCase,
)
from tests.integration.src.sqlbuild.compiler.pipeline.helpers import (
    run_compile_pipeline_for_project,
    validate_manifest_against_dbt_schema,
)

_PROJECT_YML: str = "name: demo\nadapter: duckdb\nconnection:\n  database: ':memory:'\n"

PIPELINE_TEST_CASES: list[RunCompilePipelineIntegrationTestCase] = [
    RunCompilePipelineIntegrationTestCase(
        description="single table model with no schema defaults to adapter schema",
        project_files={
            "sqlbuild_project.yml": _PROJECT_YML,
            "models/orders.sql": ("MODEL (materialized table);\n\nSELECT 1 AS order_id"),
        },
        expected_models={
            "orders": ExpectedModelEntry(
                description="table model with adapter default schema",
                expected_resolved_sql_fragment="SELECT 1 AS order_id",
                expected_logical_ddl_fragment="CREATE OR REPLACE TABLE",
                expected_manifest_compiled_code_fragment="SELECT 1 AS order_id",
            ),
        },
        expected_model_count=1,
        expected_seed_count=0,
        expected_manifest_node_count=1,
    ),
    RunCompilePipelineIntegrationTestCase(
        description="view materialization produces create or replace view DDL",
        project_files={
            "sqlbuild_project.yml": _PROJECT_YML,
            "models/active_orders.sql": (
                "MODEL (materialized view);\n\nSELECT order_id FROM orders WHERE status = 'active'"
            ),
        },
        expected_models={
            "active_orders": ExpectedModelEntry(
                description="view model with correct DDL",
                expected_resolved_sql_fragment="SELECT order_id FROM orders",
                expected_logical_ddl_fragment="CREATE OR REPLACE VIEW",
                expected_manifest_compiled_code_fragment="SELECT order_id FROM orders",
            ),
        },
        expected_model_count=1,
        expected_seed_count=0,
        expected_manifest_node_count=1,
    ),
    RunCompilePipelineIntegrationTestCase(
        description="model with explicit schema and database populates manifest target",
        project_files={
            "sqlbuild_project.yml": _PROJECT_YML,
            "models/orders.sql": (
                "MODEL (\n  materialized table\n  schema analytics\n"
                "  database warehouse\n);\n\n"
                "SELECT 1 AS order_id"
            ),
        },
        expected_models={
            "orders": ExpectedModelEntry(
                description="table model with explicit schema and database",
                expected_resolved_sql_fragment="SELECT 1 AS order_id",
                expected_logical_ddl_fragment="CREATE OR REPLACE TABLE",
                expected_manifest_compiled_code_fragment="SELECT 1 AS order_id",
            ),
        },
        expected_model_count=1,
        expected_seed_count=0,
        expected_manifest_node_count=1,
    ),
    RunCompilePipelineIntegrationTestCase(
        description="two models with ref dependency resolves ref to qualified name",
        project_files={
            "sqlbuild_project.yml": _PROJECT_YML,
            "models/stg_orders.sql": ("MODEL (materialized table);\n\nSELECT 1 AS order_id"),
            "models/fact_orders.sql": (
                'MODEL (materialized table);\n\nSELECT order_id FROM __ref("stg_orders")'
            ),
        },
        expected_models={
            "stg_orders": ExpectedModelEntry(
                description="upstream staging model",
                expected_resolved_sql_fragment="SELECT 1 AS order_id",
                expected_logical_ddl_fragment="CREATE OR REPLACE TABLE",
                expected_manifest_compiled_code_fragment="SELECT 1 AS order_id",
            ),
            "fact_orders": ExpectedModelEntry(
                description="downstream model with resolved ref",
                expected_resolved_sql_fragment="main.stg_orders",
                expected_logical_ddl_fragment="CREATE OR REPLACE TABLE",
                expected_manifest_compiled_code_fragment="main.stg_orders",
            ),
        },
        expected_model_count=2,
        expected_seed_count=0,
        expected_manifest_node_count=2,
    ),
    RunCompilePipelineIntegrationTestCase(
        description="model with source reference resolves source to qualified name",
        project_files={
            "sqlbuild_project.yml": _PROJECT_YML,
            "sources/raw.yml": (
                "sources:\n  - name: raw_payments\n    schema: main\n    table: payments\n"
            ),
            "models/stg_payments.sql": (
                'MODEL (materialized table);\n\nSELECT payment_id FROM __source("raw_payments")'
            ),
        },
        expected_models={
            "stg_payments": ExpectedModelEntry(
                description="model with resolved source reference",
                expected_resolved_sql_fragment="main.payments",
                expected_logical_ddl_fragment="CREATE OR REPLACE TABLE",
                expected_manifest_compiled_code_fragment="main.payments",
            ),
        },
        expected_model_count=1,
        expected_seed_count=0,
        expected_manifest_node_count=1,
    ),
    RunCompilePipelineIntegrationTestCase(
        description="multiple models in subdirectories preserves relative paths",
        project_files={
            "sqlbuild_project.yml": _PROJECT_YML,
            "models/staging/stg_orders.sql": ("MODEL (materialized view);\n\nSELECT 1 AS order_id"),
            "models/marts/fact_orders.sql": (
                'MODEL (materialized table);\n\nSELECT order_id FROM __ref("stg_orders")'
            ),
        },
        expected_models={
            "stg_orders": ExpectedModelEntry(
                description="staging view in subdirectory",
                expected_resolved_sql_fragment="SELECT 1 AS order_id",
                expected_logical_ddl_fragment="CREATE OR REPLACE VIEW",
                expected_manifest_compiled_code_fragment="SELECT 1 AS order_id",
            ),
            "fact_orders": ExpectedModelEntry(
                description="mart table with ref to staging view",
                expected_resolved_sql_fragment="main.stg_orders",
                expected_logical_ddl_fragment="CREATE OR REPLACE TABLE",
                expected_manifest_compiled_code_fragment="main.stg_orders",
            ),
        },
        expected_model_count=2,
        expected_seed_count=0,
        expected_manifest_node_count=2,
    ),
]


@pytest.mark.parametrize(
    "test_case",
    PIPELINE_TEST_CASES,
    ids=[case.description for case in PIPELINE_TEST_CASES],
)
def test_given_project_files_when_running_compile_pipeline_then_produces_valid_output(
    test_case: RunCompilePipelineIntegrationTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(tmp_path, test_case.project_files)

    result: CompilePipelineResult = run_compile_pipeline_for_project(
        project_dir=tmp_path,
        adapter=DuckDbAdapter(),
    )

    assert len(result.plan_output.model_entries) == test_case.expected_model_count
    assert len(result.plan_output.seed_entries) == test_case.expected_seed_count
    manifest_nodes: dict[str, object] = cast(dict[str, object], result.manifest["nodes"])
    assert len(manifest_nodes) == test_case.expected_manifest_node_count

    entry_map: dict[str, ModelPlanEntry] = {e.name: e for e in result.plan_output.model_entries}
    model_name: str
    expected: ExpectedModelEntry
    for model_name, expected in test_case.expected_models.items():
        entry: ModelPlanEntry = entry_map[model_name]
        assert expected.expected_resolved_sql_fragment in entry.resolved_sql
        assert expected.expected_logical_ddl_fragment in entry.logical_ddl
        node_id: str = f"model.demo.{model_name}"
        model_node: dict[str, object] = cast(dict[str, object], manifest_nodes[node_id])
        compiled_code: str = cast(str, model_node["compiled_code"])
        assert expected.expected_manifest_compiled_code_fragment in compiled_code

    validate_manifest_against_dbt_schema(result.manifest)


@pytest.mark.parametrize(
    "test_case",
    [
        DeferToIntegrationTestCase(
            description="defer-to resolves unselected ref to deferred environment schema",
            project_files={
                "sqlbuild_project.yml": (
                    "name: demo\n"
                    "adapter: duckdb\n"
                    "default_environment: dev\n"
                    "connection:\n"
                    "  database: ':memory:'\n"
                    "environments:\n"
                    "  dev:\n"
                    "    schema: dev_schema\n"
                    "  prod:\n"
                    "    schema: prod_schema\n"
                ),
                "models/stg_orders.sql": ("MODEL (materialized table);\n\nSELECT 1 AS order_id"),
                "models/fact_orders.sql": (
                    'MODEL (materialized table);\n\nSELECT order_id FROM __ref("stg_orders")'
                ),
            },
            defer_to="prod",
            select=("fact_orders",),
            expected_model_count=1,
            expected_resolved_sql_fragments={
                "fact_orders": "prod_schema.stg_orders",
            },
        ),
    ],
    ids=["defer-to resolves unselected ref to deferred environment schema"],
)
def test_given_project_with_defer_to_when_compiling_then_resolves_refs_to_deferred_env(
    test_case: DeferToIntegrationTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    db_path: str = str(tmp_path / "test.duckdb")
    project_files: dict[str, str] = {
        k: v.replace(":memory:", db_path) for k, v in test_case.project_files.items()
    }
    write_repo_files(tmp_path, project_files)

    import duckdb

    conn: duckdb.DuckDBPyConnection = duckdb.connect(db_path)
    conn.execute("CREATE SCHEMA IF NOT EXISTS prod_schema")
    conn.execute("CREATE TABLE prod_schema.stg_orders (order_id INTEGER)")
    conn.close()

    result: CompilePipelineResult = run_compile_pipeline_for_project(
        project_dir=tmp_path,
        adapter=DuckDbAdapter(),
        defer_to=test_case.defer_to,
        select=test_case.select,
    )

    assert len(result.plan_output.model_entries) == test_case.expected_model_count
    entry_map: dict[str, ModelPlanEntry] = {e.name: e for e in result.plan_output.model_entries}
    model_name: str
    expected_fragment: str
    for model_name, expected_fragment in test_case.expected_resolved_sql_fragments.items():
        assert expected_fragment in entry_map[model_name].resolved_sql
