from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.adapters.snowflake.classes.snowflake_adapter import SnowflakeAdapter
from sqlbuild.cli.commands.helpers.compile.target_writer import write_compile_target
from sqlbuild.compiler.compile.models.core import CompiledProject
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.graph import build_project_graph
from sqlbuild.compiler.pipeline.main.project import compile_project
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.compiler.planner.models import ModelPlanEntry
from tests.integration.src.sqlbuild.compiler.pipeline._test_types import (
    AppendCursorPipelineIntegrationTestCase,
    CompileProgressIntegrationTestCase,
    DeferToIntegrationTestCase,
    ExpectedModelEntry,
    RunCompilePipelineIntegrationTestCase,
    SnowflakeTargetValidationIntegrationTestCase,
    SqlAnalysisChainCompileTargetIntegrationTestCase,
)
from tests.integration.src.sqlbuild.compiler.pipeline.helpers import (
    build_manifest_for_pipeline_result,
    run_compile_pipeline_for_project,
    validate_manifest_against_dbt_schema,
)

_PROJECT_TOML: str = 'name = "demo"\nadapter = "duckdb"\n\n[connection]\ndatabase = ":memory:"\n'


@pytest.mark.parametrize(
    "test_case",
    [
        RunCompilePipelineIntegrationTestCase(
            description="single table model with no schema defaults to adapter schema",
            project_files={
                "sqlbuild_project.toml": _PROJECT_TOML,
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
                "sqlbuild_project.toml": _PROJECT_TOML,
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
                "sqlbuild_project.toml": _PROJECT_TOML,
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
                "sqlbuild_project.toml": _PROJECT_TOML,
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
                "sqlbuild_project.toml": _PROJECT_TOML,
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
                "sqlbuild_project.toml": _PROJECT_TOML,
                "models/staging/stg_orders.sql": (
                    "MODEL (materialized view);\n\nSELECT 1 AS order_id"
                ),
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
    ],
    ids=lambda case: case.description,
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
    manifest: dict[str, object] = build_manifest_for_pipeline_result(
        project_dir=tmp_path,
        result=result,
        project_name="demo",
        adapter_type="duckdb",
    )
    manifest_nodes: dict[str, object] = cast(dict[str, object], manifest["nodes"])
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

    validate_manifest_against_dbt_schema(manifest)


@pytest.mark.parametrize(
    "test_case",
    [
        RunCompilePipelineIntegrationTestCase(
            description="run selector resolves Python task without SQL-only planning",
            project_files={
                "sqlbuild_project.toml": _PROJECT_TOML,
                "models/orders.sql": "MODEL (materialized table);\n\nSELECT 1 AS order_id",
                "tasks/orders.py": (
                    "from sqlbuild.tasks import task\n\n"
                    "@task\n"
                    "def prepare_orders(ctx):\n"
                    "    return ctx.result(payload={'ok': True})\n"
                ),
            },
            expected_models={},
            expected_model_count=0,
            expected_seed_count=0,
            expected_manifest_node_count=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_python_run_selector_when_running_compile_pipeline_then_tracks_python_nodes(
    test_case: RunCompilePipelineIntegrationTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(tmp_path, test_case.project_files)

    result: CompilePipelineResult = run_compile_pipeline_for_project(
        project_dir=tmp_path,
        adapter=DuckDbAdapter(),
        select=("task:prepare_orders",),
        resolve_python_run_selectors=True,
    )

    assert len(result.plan_output.model_entries) == test_case.expected_model_count
    assert len(result.plan_output.seed_entries) == test_case.expected_seed_count
    assert result.python_node_names == frozenset({"prepare_orders"})


@pytest.mark.parametrize(
    "test_case",
    [
        CompileProgressIntegrationTestCase(
            description="reports compile progress from compile pipeline",
            project_files={
                "sqlbuild_project.toml": _PROJECT_TOML,
                "models/orders.sql": "MODEL (materialized table);\n\nSELECT 1 AS order_id",
            },
            expected_progress_prefixes=("Compiling project...", "Compiled project."),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_progress_callback_when_running_compile_pipeline_then_reports_compile_progress(
    test_case: CompileProgressIntegrationTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    progress_messages: list[str] = []
    write_repo_files(tmp_path, test_case.project_files)

    run_compile_pipeline_for_project(
        project_dir=tmp_path,
        adapter=DuckDbAdapter(),
        on_progress=progress_messages.append,
    )

    expected_prefix: str
    for expected_prefix in test_case.expected_progress_prefixes:
        assert any(message.startswith(expected_prefix) for message in progress_messages)


@pytest.mark.parametrize(
    "test_case",
    [
        CompileProgressIntegrationTestCase(
            description="reports compile progress from project graph build",
            project_files={
                "sqlbuild_project.toml": _PROJECT_TOML,
                "models/orders.sql": "MODEL (materialized table);\n\nSELECT 1 AS order_id",
            },
            expected_progress_prefixes=("Compiling project...", "Compiled project."),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_progress_callback_when_building_project_graph_then_reports_compile_progress(
    test_case: CompileProgressIntegrationTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    progress_messages: list[str] = []
    write_repo_files(tmp_path, test_case.project_files)
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(project_dir=tmp_path)

    build_project_graph(
        discovered_inputs=discovered_inputs,
        adapter=DuckDbAdapter(),
        no_sql_validation=True,
        on_progress=progress_messages.append,
    )

    expected_prefix: str
    for expected_prefix in test_case.expected_progress_prefixes:
        assert any(message.startswith(expected_prefix) for message in progress_messages)


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeTargetValidationIntegrationTestCase(
            description="snowflake compile requires explicit target database and schema",
            project_files={
                "sqlbuild_project.toml": (
                    'name = "demo"\nadapter = "duckdb"\n\n[connection]\ndatabase = "demo.duckdb"\n'
                ),
                "sqlbuild_local.toml": (
                    'adapter = "snowflake"\n\n'
                    "[connection]\n"
                    'account = "${ENV:TEST_ACCOUNT}"\n'
                    'warehouse = "TEST_WH"\n'
                    'database = "TEST_DB"\n'
                    'schema = "TEST_SCHEMA"\n'
                ),
                "models/stg_orders.sql": "MODEL (materialized view);\n\nSELECT 1 AS order_id\n",
            },
            expected_error_fragment="snowflake execution requires explicit target database, schema",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_snowflake_local_override_without_target_namespace_when_compiling_then_it_fails_early(
    test_case: SnowflakeTargetValidationIntegrationTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEST_ACCOUNT", "test-account")
    write_repo_files(tmp_path, test_case.project_files)
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(project_dir=tmp_path)

    with pytest.raises(ValueError, match=test_case.expected_error_fragment):
        compile_project(
            discovered_inputs=discovered_inputs,
            adapter=SnowflakeAdapter(),
            no_sql_validation=True,
        )


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeTargetValidationIntegrationTestCase(
            description="snowflake local target namespace resolves model target",
            project_files={
                "sqlbuild_project.toml": 'name = "demo"\nadapter = "duckdb"\n',
                "sqlbuild_local.toml": (
                    'adapter = "snowflake"\n'
                    'target = "dev"\n\n'
                    "[connection]\n"
                    'database = "${ENV:TEST_DB}"\n'
                    'schema = "${ENV:TEST_SCHEMA}"\n\n'
                    "[targets.dev]\n"
                    'database = "${ENV:TEST_DB}"\n'
                    'schema = "${ENV:TEST_SCHEMA}"\n'
                ),
                "models/stg_orders.sql": "MODEL (materialized view);\n\nSELECT 1 AS order_id\n",
            },
            expected_database="LOCAL_DB",
            expected_schema="LOCAL_SCHEMA",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_snowflake_local_target_namespace_when_compiling_then_targets_resolve(
    test_case: SnowflakeTargetValidationIntegrationTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEST_DB", "LOCAL_DB")
    monkeypatch.setenv("TEST_SCHEMA", "LOCAL_SCHEMA")
    write_repo_files(tmp_path, test_case.project_files)

    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(project_dir=tmp_path)
    project: CompiledProject = compile_project(
        discovered_inputs=discovered_inputs,
        adapter=SnowflakeAdapter(),
        no_sql_validation=True,
    )

    assert project.models[0].destination.database == test_case.expected_database
    assert project.models[0].destination.schema == test_case.expected_schema


@pytest.mark.parametrize(
    "test_case",
    [
        DeferToIntegrationTestCase(
            description="defer-to resolves unselected ref to deferred target schema",
            project_files={
                "sqlbuild_project.toml": (
                    'name = "demo"\n'
                    'adapter = "duckdb"\n'
                    'default_target = "dev"\n\n'
                    "[connection]\n"
                    'database = ":memory:"\n\n'
                    "[targets.dev]\n"
                    'schema = "dev_schema"\n\n'
                    "[targets.prod]\n"
                    'schema = "prod_schema"\n'
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
    ids=lambda case: case.description,
)
def test_given_project_with_defer_to_when_compiling_then_resolves_refs_to_deferred_target(
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


@pytest.mark.parametrize(
    "test_case",
    [
        SqlAnalysisChainCompileTargetIntegrationTestCase(
            description="chain test compile target uses flat generated ctes",
            project_files={
                "sqlbuild_project.toml": (
                    'name = "demo"\n'
                    'adapter = "duckdb"\n\n'
                    "[connection]\n"
                    'database = ":memory:"\n\n'
                    "[settings]\n"
                    "sql_analysis = true\n"
                ),
                "models/stg_orders.sql": (
                    'MODEL (materialized table);\n\nSELECT id, amount FROM __source("raw")'
                ),
                "models/fact_orders.sql": (
                    "MODEL (materialized table);\n\n"
                    "WITH local_helper AS (SELECT 1 AS one) "
                    'SELECT id, amount + one AS adjusted FROM __ref("stg_orders") '
                    "CROSS JOIN local_helper"
                ),
                "sources/raw.yml": "sources:\n  - name: raw\n    schema: main\n    table: raw\n",
                "tests/unit/test_chain.sql": (
                    "TEST();\n\n"
                    "WITH\n"
                    "__source__raw AS (SELECT 1 AS id, 100 AS amount),\n"
                    "__expected__stg_orders AS (SELECT 1 AS id, 100 AS amount),\n"
                    "__expected__fact_orders AS (SELECT 1 AS id, 101 AS adjusted)\n"
                    "SELECT 1\n"
                ),
            },
            compiled_test_path=(
                "target/compiled/tests/_chain_/fact_orders__stg_orders/test_chain.sql"
            ),
            expected_fragments=(
                "WITH __source__raw AS (",
                "__ref__stg_orders AS (",
                "FROM __source__raw",
                "local_helper AS (",
                "__actual__fact_orders AS (",
                "FROM __ref__stg_orders",
                "'stg_orders' AS model_name",
            ),
            unexpected_fragments=(
                "__ref__stg_orders AS (WITH",
                "__REF(",
                "__SOURCE(",
                "\n\nWITH",
                "__actual_0 AS (WITH",
                "__actual_0 AS (\n  WITH",
                "__actual_1 AS (\n  WITH",
                "__actual_0",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_sql_analysis_enabled_chain_test_when_writing_compile_target_then_uses_ctes(
    test_case: SqlAnalysisChainCompileTargetIntegrationTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(tmp_path, test_case.project_files)

    result: CompilePipelineResult = run_compile_pipeline_for_project(
        project_dir=tmp_path,
        adapter=DuckDbAdapter(),
    )
    write_compile_target(
        target_dir=tmp_path / "target",
        adapter=DuckDbAdapter(),
        plan_output=result.plan_output,
    )

    compiled_test_sql: str = (tmp_path / test_case.compiled_test_path).read_text(encoding="utf-8")

    expected_fragment: str
    for expected_fragment in test_case.expected_fragments:
        assert expected_fragment in compiled_test_sql
    unexpected_fragment: str
    for unexpected_fragment in test_case.unexpected_fragments:
        assert unexpected_fragment not in compiled_test_sql


@pytest.mark.parametrize(
    "test_case",
    [
        AppendCursorPipelineIntegrationTestCase(
            description="append cursor defaults to inclusive lower bound in resolved sql",
            append_cursor_inclusive=True,
            expected_resolved_sql_fragment="WHERE ordered_at >= TIMESTAMP '2026-01-01 00:00:00'",
        ),
        AppendCursorPipelineIntegrationTestCase(
            description="append cursor can use exclusive lower bound in resolved sql",
            append_cursor_inclusive=False,
            expected_resolved_sql_fragment="WHERE ordered_at > TIMESTAMP '2026-01-01 00:00:00'",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_append_cursor_model_when_compiling_then_sql_uses_expected_lower_bound(
    test_case: AppendCursorPipelineIntegrationTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    db_path: Path = tmp_path / "append_cursor.duckdb"
    model_header: str = (
        "MODEL (\n"
        "  materialized incremental,\n"
        "  incremental_strategy append,\n"
        "  cursor ordered_at,\n"
        "  cursor_type timestamp,\n"
        "  cursor_grain second,\n"
        + ("  append_cursor_inclusive false,\n" if not test_case.append_cursor_inclusive else "")
        + ");\n\n"
        + 'SELECT id, ordered_at FROM __source("raw_orders")'
    )
    write_repo_files(
        tmp_path,
        {
            "sqlbuild_project.toml": (
                f'name = "demo"\nadapter = "duckdb"\n\n[connection]\ndatabase = "{db_path}"\n'
            ),
            "sources/raw.yml": (
                "sources:\n  - name: raw_orders\n    schema: main\n    table: raw_orders\n"
            ),
            "models/orders.sql": model_header,
        },
    )

    import duckdb

    connection: duckdb.DuckDBPyConnection = duckdb.connect(str(db_path))
    connection.execute("CREATE TABLE main.raw_orders (id INTEGER, ordered_at TIMESTAMP)")
    connection.execute(
        "INSERT INTO main.raw_orders VALUES (1, '2026-01-01 00:00:00'), (2, '2026-01-01 01:00:00')"
    )
    connection.execute("CREATE TABLE main.orders (id INTEGER, ordered_at TIMESTAMP)")
    connection.execute("INSERT INTO main.orders VALUES (1, '2026-01-01 00:00:00')")
    connection.close()

    result: CompilePipelineResult = run_compile_pipeline_for_project(
        project_dir=tmp_path,
        adapter=DuckDbAdapter(),
    )

    entry_map: dict[str, ModelPlanEntry] = {e.name: e for e in result.plan_output.model_entries}
    assert test_case.expected_resolved_sql_fragment in entry_map["orders"].resolved_sql
