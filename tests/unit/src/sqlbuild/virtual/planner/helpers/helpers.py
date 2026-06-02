from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.compile.models.core import (
    CompiledFunction,
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationTarget,
    CompileModelConfig,
    FunctionArgument,
)
from sqlbuild.compiler.compile.types import CompiledResourceType, FunctionLanguage
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.planner.helpers.graph import (
    build_downstream_deps,
    build_upstream_deps,
)
from sqlbuild.spec.models.project import SettingsConfig


def build_virtual_planner_test_project(
    *,
    upstream_query_sql: str,
    downstream_query_sql: str,
    downstream_depends_on_dim_customers: bool = False,
    upstream_model_name: str = "stg_orders",
    upstream_schema: str = "staging",
    upstream_materialized: str = "table",
    upstream_extra_config: dict[str, object] | None = None,
) -> ProjectGraph:
    function: CompiledFunction = CompiledFunction(
        key=CompiledObjectKey(resource_type=CompiledResourceType.FUNCTION, name="normalize_order"),
        deps=(),
        name="normalize_order",
        relative_path=Path("functions/sql/normalize_order.sql"),
        arguments=(FunctionArgument(name="value", type="INTEGER"),),
        returns="INTEGER",
        body_sql="value + 1",
        target=CompiledRelationTarget(
            database=None,
            schema="staging",
            name="normalize_order",
            qualified_name="staging.normalize_order",
        ),
        fingerprint_target=CompiledRelationTarget(
            database=None,
            schema="staging",
            name="normalize_order",
            qualified_name="staging.normalize_order",
        ),
        language=FunctionLanguage.SQL,
    )
    upstream_config_values: dict[str, object] = {
        "materialized": upstream_materialized,
        "schema": upstream_schema,
    }
    if upstream_extra_config is not None:
        upstream_config_values.update(upstream_extra_config)
    upstream_model: CompiledModel = CompiledModel(
        key=CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name=upstream_model_name),
        deps=(),
        name=upstream_model_name,
        relative_path=Path(f"models/{upstream_model_name}.sql"),
        query_sql=upstream_query_sql,
        config=CompileModelConfig(values=upstream_config_values),
        target=CompiledRelationTarget(
            database=None,
            schema=upstream_schema,
            name=upstream_model_name,
            qualified_name=f"{upstream_schema}.{upstream_model_name}",
        ),
    )
    downstream_model: CompiledModel = CompiledModel(
        key=CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name="fact_orders"),
        deps=(upstream_model.key, function.key),
        name="fact_orders",
        relative_path=Path("models/fact_orders.sql"),
        query_sql=downstream_query_sql,
        config=CompileModelConfig(values={"materialized": "table"}),
        target=CompiledRelationTarget(
            database=None,
            schema="marts",
            name="fact_orders",
            qualified_name="marts.fact_orders",
        ),
    )
    unrelated_model: CompiledModel = CompiledModel(
        key=CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name="dim_customers"),
        deps=(),
        name="dim_customers",
        relative_path=Path("models/dim_customers.sql"),
        query_sql="SELECT 1 AS customer_id",
        config=CompileModelConfig(values={"materialized": "table"}),
        target=CompiledRelationTarget(
            database=None,
            schema="marts",
            name="dim_customers",
            qualified_name="marts.dim_customers",
        ),
    )
    downstream_deps: tuple[CompiledObjectKey, ...] = (
        (upstream_model.key, function.key, unrelated_model.key)
        if downstream_depends_on_dim_customers
        else (upstream_model.key, function.key)
    )
    downstream_model = CompiledModel(
        key=downstream_model.key,
        deps=downstream_deps,
        name=downstream_model.name,
        relative_path=downstream_model.relative_path,
        query_sql=downstream_model.query_sql,
        config=downstream_model.config,
        target=downstream_model.target,
    )
    project: CompiledProject = CompiledProject(
        run_id="test_run",
        effective_target_name="dev",
        effective_connection={},
        effective_vars={},
        settings=SettingsConfig(),
        models=(upstream_model, downstream_model, unrelated_model),
        functions=(function,),
    )
    upstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = build_upstream_deps(
        project
    )
    downstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = build_downstream_deps(
        upstream_deps
    )
    all_keys: dict[str, CompiledObjectKey] = {
        upstream_model.name: upstream_model.key,
        downstream_model.name: downstream_model.key,
        unrelated_model.name: unrelated_model.key,
        function.name: function.key,
    }
    return ProjectGraph(
        project=project,
        upstream_deps=upstream_deps,
        downstream_deps=downstream_deps,
        tag_index={},
        path_index={},
        all_keys=all_keys,
    )
