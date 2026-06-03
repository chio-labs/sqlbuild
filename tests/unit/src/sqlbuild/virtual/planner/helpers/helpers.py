from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.compile.models.core import (
    CompiledFunction,
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationDestination,
    CompiledSource,
    CompileModelConfig,
    FunctionArgument,
)
from sqlbuild.compiler.compile.types import CompiledResourceType, FunctionLanguage
from sqlbuild.compiler.discovery.models import DiscoveredSourceFile
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.planner.helpers.graph import (
    build_downstream_deps,
    build_upstream_deps,
)
from sqlbuild.spec.models.project import SettingsConfig
from sqlbuild.spec.models.schema import SchemaColumn, SchemaModelEntry
from sqlbuild.spec.models.source import SourceEntry


def build_virtual_planner_test_project(
    *,
    upstream_query_sql: str,
    downstream_query_sql: str,
    function_body_sql: str = "value + 1",
    downstream_depends_on_dim_customers: bool = False,
    upstream_model_name: str = "stg_orders",
    upstream_schema: str = "staging",
    upstream_materialized: str = "table",
    upstream_extra_config: dict[str, object] | None = None,
    upstream_source_name: str = "raw.orders",
    upstream_schema_columns: tuple[SchemaColumn, ...] = (),
) -> ProjectGraph:
    function: CompiledFunction = CompiledFunction(
        key=CompiledObjectKey(resource_type=CompiledResourceType.FUNCTION, name="normalize_order"),
        deps=(),
        name="normalize_order",
        relative_path=Path("functions/sql/normalize_order.sql"),
        arguments=(FunctionArgument(name="value", type="INTEGER"),),
        returns="INTEGER",
        body_sql=function_body_sql,
        destination=CompiledRelationDestination(
            database=None,
            schema="staging",
            name="normalize_order",
            qualified_name="staging.normalize_order",
        ),
        fingerprint_destination=CompiledRelationDestination(
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
    source_entry: SourceEntry = SourceEntry(name=upstream_source_name, table="raw_orders")
    upstream_source: CompiledSource = CompiledSource(
        key=CompiledObjectKey(resource_type=CompiledResourceType.SOURCE, name=upstream_source_name),
        deps=(),
        name=upstream_source_name,
        source_entry=source_entry,
        source_file=DiscoveredSourceFile(
            file_path=Path("sources/raw.yml"),
            relative_path=Path("sources/raw.yml"),
            contents="",
            source_entries=(source_entry,),
        ),
    )
    upstream_model: CompiledModel = CompiledModel(
        key=CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name=upstream_model_name),
        deps=(upstream_source.key,),
        name=upstream_model_name,
        relative_path=Path(f"models/{upstream_model_name}.sql"),
        query_sql=upstream_query_sql,
        config=CompileModelConfig(values=upstream_config_values),
        schema_entry=(
            SchemaModelEntry(name=upstream_model_name, columns=upstream_schema_columns)
            if upstream_schema_columns
            else None
        ),
        destination=CompiledRelationDestination(
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
        destination=CompiledRelationDestination(
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
        destination=CompiledRelationDestination(
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
        destination=downstream_model.destination,
    )
    project: CompiledProject = CompiledProject(
        run_id="test_run",
        effective_target_name="dev",
        effective_connection={},
        effective_vars={},
        settings=SettingsConfig(),
        models=(upstream_model, downstream_model, unrelated_model),
        sources=(upstream_source,),
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
        upstream_source.name: upstream_source.key,
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
