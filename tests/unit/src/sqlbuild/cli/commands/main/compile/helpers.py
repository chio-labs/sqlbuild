from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlbuild.adapter.contract.models import LifeCycleEvent, QueryResult
from sqlbuild.adapter.contract.types import LifeCycleEventKind
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.auditing.types import (
    AuditAttachmentKind,
    AuditRunScope,
    AuditSeverity,
)
from sqlbuild.compiler.compile.models import (
    CompiledFunction,
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationLocation,
    CompileModelConfig,
    FunctionArgument,
)
from sqlbuild.compiler.compile.types import CompiledResourceType, FunctionLanguage
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.planner.models import (
    AuditPlanEntry,
    ChainStep,
    FunctionPlanEntry,
    ModelPlanEntry,
    PlanOutput,
    SeedPlanEntry,
    SqlTestPlanEntry,
)
from sqlbuild.compiler.planner.types import MaterializationType, PlanAction, PlanReason
from sqlbuild.executor.build.models import (
    BuildExecutionResult,
    FunctionExecutionResult,
)
from sqlbuild.executor.build.types import BuildStatus
from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.executor.scheduling.types import ExecutionStatus
from sqlbuild.spec.contracts.models import SeedCsvSettings
from tests.unit.src.sqlbuild.cli.commands.main.dag.helpers import (
    prepare_python_dag_project,
)


class NoConnectDuckDbAdapter(DuckDbAdapter):
    """DuckDB adapter test double that fails if compile opens a connection."""

    def connect(self, config: dict[str, Any]) -> Any:
        del config
        raise AssertionError("compile should not connect")

    def _execute(self, connection: Any, sql: str) -> Any:
        del connection, sql
        raise AssertionError("compile should not execute SQL")

    def query(self, connection: Any, sql: str, *, limit: int | None) -> QueryResult:
        del connection, sql, limit
        raise AssertionError("compile should not query")

    def close(self, connection: Any) -> None:
        del connection
        raise AssertionError("compile should not close a connection")


def prepare_static_compile_project(root: Path) -> Path:
    """Create a minimal local project for offline compile command tests."""

    project_dir: Path = root / "project"
    models_dir: Path = project_dir / "models"
    models_dir.mkdir(parents=True)
    (project_dir / "sqlbuild_project.toml").write_text(
        "\n".join(
            (
                'name = "offline_compile"',
                'adapter = "duckdb"',
                'default_target = "dev"',
                "",
                "[targets.dev]",
                'schema = "main"',
            )
        )
        + "\n",
        encoding="utf-8",
    )
    (models_dir / "orders.sql").write_text(
        "MODEL (materialized view);\n\nSELECT 1 AS order_id\n",
        encoding="utf-8",
    )
    return project_dir


def prepare_python_compile_project(root: Path) -> Path:
    """Create a local project with Python nodes for compile DAG tests."""

    project_dir: Path = prepare_python_dag_project(root)
    (project_dir / "sqlbuild_project.toml").write_text(
        "\n".join(
            (
                'name = "offline_compile"',
                'adapter = "duckdb"',
                'default_target = "dev"',
                "",
                "[targets.dev]",
                'schema = "main"',
            )
        )
        + "\n",
        encoding="utf-8",
    )
    return project_dir


def build_target_writer_plan_output() -> PlanOutput:
    """Build a plan output covering every target writer artifact type."""

    model_key: CompiledObjectKey = CompiledObjectKey(
        resource_type=CompiledResourceType.MODEL,
        name="orders",
    )
    seed_key: CompiledObjectKey = CompiledObjectKey(
        resource_type=CompiledResourceType.SEED,
        name="country_codes",
    )
    audit_key: CompiledObjectKey = CompiledObjectKey(
        resource_type=CompiledResourceType.AUDIT,
        name="not_null",
    )
    test_key: CompiledObjectKey = CompiledObjectKey(
        resource_type=CompiledResourceType.SQL_TEST,
        name="orders_chain",
    )
    function_key: CompiledObjectKey = CompiledObjectKey(
        resource_type=CompiledResourceType.UDF,
        name="is_completed_order",
    )
    python_function_key: CompiledObjectKey = CompiledObjectKey(
        resource_type=CompiledResourceType.UDF,
        name="is_completed_order_py",
    )
    target: CompiledRelationLocation = CompiledRelationLocation(
        database=None,
        schema="analytics",
        name="orders",
        qualified_name="analytics.orders",
    )
    return PlanOutput(
        model_entries=(
            ModelPlanEntry(
                key=model_key,
                name="orders",
                relative_path=Path("staging/orders.sql"),
                materialization_type=MaterializationType.TABLE,
                action=PlanAction.CREATE_TABLE,
                reason=PlanReason.FIRST_RUN,
                destination=target,
                fingerprint_query_sql="SELECT 1 AS order_id",
                resolved_sql="SELECT 1 AS order_id",
                logical_ddl="CREATE TABLE analytics.orders AS SELECT 1 AS order_id",
            ),
        ),
        seed_entries=(
            SeedPlanEntry(
                key=seed_key,
                name="country_codes",
                destination=target,
                file_path=Path("seeds/country_codes.csv"),
                columns=(),
                csv_settings=SeedCsvSettings(),
            ),
        ),
        function_entries=(
            FunctionPlanEntry(
                key=function_key,
                name="is_completed_order",
                relative_path=Path("functions/sql/is_completed_order.sql"),
                destination=CompiledRelationLocation(
                    database=None,
                    schema="analytics",
                    name="is_completed_order",
                    qualified_name="analytics.is_completed_order",
                ),
                fingerprint_destination=CompiledRelationLocation(
                    database=None,
                    schema="analytics",
                    name="is_completed_order",
                    qualified_name="analytics.is_completed_order",
                ),
                arguments=(FunctionArgument(name="order_status", type="VARCHAR"),),
                returns="BOOLEAN",
                body_sql="order_status = 'completed'",
                fingerprint_query_sql="order_status = 'completed'",
            ),
            FunctionPlanEntry(
                key=python_function_key,
                name="is_completed_order_py",
                relative_path=Path("functions/python/is_completed_order_py.py"),
                destination=CompiledRelationLocation(
                    database=None,
                    schema="analytics",
                    name="is_completed_order_py",
                    qualified_name="analytics.is_completed_order_py",
                ),
                fingerprint_destination=CompiledRelationLocation(
                    database=None,
                    schema="analytics",
                    name="is_completed_order_py",
                    qualified_name="analytics.is_completed_order_py",
                ),
                arguments=(FunctionArgument(name="order_status", type="VARCHAR"),),
                returns="BOOLEAN",
                body_sql=(
                    "def main(order_status: str | None) -> bool:\n"
                    "    return order_status == 'completed'"
                ),
                fingerprint_query_sql=(
                    "def main(order_status: str | None) -> bool:\n"
                    "    return order_status == 'completed'"
                ),
                language=FunctionLanguage.PYTHON,
                entry_point="main",
            ),
        ),
        audit_entries=(
            AuditPlanEntry(
                key=audit_key,
                name="not_null",
                resolved_sql="SELECT order_id FROM analytics.orders WHERE order_id IS NULL",
                unresolved_sql='SELECT order_id FROM __ref("orders") WHERE order_id IS NULL',
                attachment_kind=AuditAttachmentKind.MODEL,
                severity=AuditSeverity.WARN,
                requested_run_scope=AuditRunScope.FINAL,
                effective_run_scope=AuditRunScope.FINAL,
                attached_target_name="orders",
                attached_column_name="order_id",
            ),
        ),
        test_entries=(
            SqlTestPlanEntry(
                key=test_key,
                name="orders_chain",
                chain=(
                    ChainStep(
                        model_name="stg_orders",
                        resolved_sql="SELECT 1 AS order_id",
                        expected_cte_sql="SELECT 1 AS order_id",
                    ),
                    ChainStep(
                        model_name="orders",
                        resolved_sql="SELECT order_id FROM stg_orders",
                        expected_cte_sql="SELECT 1 AS order_id",
                    ),
                ),
            ),
        ),
    )


def read_target_files(target_dir: Path, expected_files: dict[str, str]) -> dict[str, str]:
    """Read expected target files into a comparable mapping."""

    return {
        relative_path: (target_dir / relative_path).read_text(encoding="utf-8")
        for relative_path in expected_files
    }


def build_static_target_writer_project() -> CompiledProject:
    """Build compiled project state for offline compile target writer tests."""

    model_key: CompiledObjectKey = CompiledObjectKey(
        resource_type=CompiledResourceType.MODEL,
        name="orders",
    )
    function_key: CompiledObjectKey = CompiledObjectKey(
        resource_type=CompiledResourceType.UDF,
        name="is_completed_order",
    )
    return CompiledProject(
        run_id="run-1",
        effective_target_name="dev",
        effective_connection={},
        effective_vars={},
        models=(
            CompiledModel(
                key=model_key,
                deps=(),
                name="orders",
                relative_path=Path("staging/orders.sql"),
                query_sql="SELECT 2 AS order_id",
                config=CompileModelConfig(values={}),
                destination=CompiledRelationLocation(
                    database=None,
                    schema="analytics",
                    name="orders",
                    qualified_name="analytics.orders",
                ),
            ),
        ),
        functions=(
            CompiledFunction(
                key=function_key,
                deps=(),
                name="is_completed_order",
                relative_path=Path("functions/sql/is_completed_order.sql"),
                arguments=(FunctionArgument(name="order_status", type="VARCHAR"),),
                returns="BOOLEAN",
                body_sql="order_status = 'completed'",
                destination=CompiledRelationLocation(
                    database=None,
                    schema="analytics",
                    name="is_completed_order",
                    qualified_name="analytics.is_completed_order",
                ),
                fingerprint_destination=CompiledRelationLocation(
                    database=None,
                    schema="analytics",
                    name="is_completed_order",
                    qualified_name="analytics.is_completed_order",
                ),
            ),
        ),
    )


def build_compile_output_graph(*, model_names: tuple[str, ...]) -> ProjectGraph:
    """Build a static project graph for compile output formatter tests."""

    models: list[CompiledModel] = []
    upstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = {}
    all_keys: dict[str, CompiledObjectKey] = {}
    name: str
    for name in model_names:
        key: CompiledObjectKey = CompiledObjectKey(
            resource_type=CompiledResourceType.MODEL,
            name=name,
        )
        models.append(
            CompiledModel(
                key=key,
                deps=(),
                name=name,
                relative_path=Path(f"models/{name}.sql"),
                query_sql="SELECT 1 AS id",
                config=CompileModelConfig(values={}),
                destination=CompiledRelationLocation(
                    database=None,
                    schema="analytics",
                    name=name,
                    qualified_name=f"analytics.{name}",
                ),
                inferred_columns=(),
            )
        )
        upstream_deps[key] = ()
        all_keys[name] = key

    project: CompiledProject = CompiledProject(
        run_id="run-1",
        effective_target_name="dev",
        effective_connection={},
        effective_vars={},
        models=tuple(models),
    )
    return ProjectGraph(
        project=project,
        upstream_deps=upstream_deps,
        downstream_deps={key: () for key in upstream_deps},
        tag_index={},
        path_index={key: "" for key in upstream_deps},
        all_keys=all_keys,
    )


def build_linear_compile_output_graph(*, model_count: int) -> ProjectGraph:
    """Build a static project graph with one model depending on the previous model."""

    graph: ProjectGraph = build_compile_output_graph(
        model_names=tuple(f"model_{index:05d}" for index in range(model_count))
    )
    upstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = {}
    downstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = {
        model.key: () for model in graph.project.models
    }
    first_model: CompiledModel = graph.project.models[0]
    upstream_deps[first_model.key] = ()
    for previous_model, model in zip(graph.project.models, graph.project.models[1:], strict=False):
        upstream_deps[model.key] = (previous_model.key,)
        downstream_deps[previous_model.key] = (
            *downstream_deps[previous_model.key],
            model.key,
        )
    return ProjectGraph(
        project=graph.project,
        upstream_deps=upstream_deps,
        downstream_deps=downstream_deps,
        tag_index=graph.tag_index,
        path_index=graph.path_index,
        all_keys=graph.all_keys,
    )


def build_compile_output_model_names(model_count: int) -> tuple[str, ...]:
    """Build model names for compile output formatter cases."""

    special_names: tuple[str, ...] = (
        "short",
        "hourly_activity_with_daily_context",
        "extremely_long_model_name_that_should_be_truncated_in_human_output",
    )
    generated_names: tuple[str, ...] = tuple(f"model_{index:03d}" for index in range(model_count))
    return {3: special_names}.get(model_count, generated_names)


def build_runtime_target_execution_result() -> BuildExecutionResult:
    return BuildExecutionResult(
        status=BuildStatus.SUCCESS,
        model_results=(
            ModelExecutionResult(
                model_name="orders",
                status=ExecutionStatus.SUCCESS,
                lifecycle_events=(
                    LifeCycleEvent(
                        kind=LifeCycleEventKind.SQL,
                        content="DROP TABLE IF EXISTS analytics.orders__staging",
                    ),
                    LifeCycleEvent(
                        kind=LifeCycleEventKind.LOG,
                        content="building partition 2024-01-01",
                    ),
                    LifeCycleEvent(
                        kind=LifeCycleEventKind.SQL,
                        content="CREATE OR REPLACE TABLE analytics.orders__staging "
                        "AS SELECT 1 AS order_id",
                    ),
                ),
            ),
        ),
        function_results=(
            FunctionExecutionResult(
                function_name="is_completed_order",
                status=ExecutionStatus.SUCCESS,
                function_kind="udf",
                lifecycle_events=(
                    LifeCycleEvent(
                        kind=LifeCycleEventKind.SQL,
                        content=(
                            "CREATE OR REPLACE FUNCTION analytics.is_completed_order"
                            "(order_status VARCHAR) RETURNS BOOLEAN"
                        ),
                    ),
                ),
            ),
            FunctionExecutionResult(
                function_name="is_completed_order_py",
                status=ExecutionStatus.SUCCESS,
                function_kind="udf",
                lifecycle_events=(
                    LifeCycleEvent(
                        kind=LifeCycleEventKind.SQL,
                        content=(
                            "REGISTER PYTHON FUNCTION analytics.is_completed_order_py"
                            "(VARCHAR) RETURNS BOOLEAN"
                        ),
                    ),
                ),
            ),
        ),
        success_count=1,
    )
