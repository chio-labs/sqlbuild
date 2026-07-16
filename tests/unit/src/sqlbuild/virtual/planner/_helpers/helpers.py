from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from types import MappingProxyType
from typing import cast

from sqlbuild.compiler.compile.models import (
    CompiledFunction,
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationLocation,
    CompiledSeed,
    CompiledSource,
    CompileModelConfig,
    FunctionArgument,
)
from sqlbuild.compiler.compile.types import CompiledResourceType, FunctionLanguage
from sqlbuild.compiler.discovery.models import (
    DiscoveredSchemaFile,
    DiscoveredSeedFile,
    DiscoveredSourceFile,
)
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.planner._helpers.graph.core import (
    build_downstream_deps,
    build_execution_upstream_deps,
)
from sqlbuild.spec.contracts.models import (
    SchemaColumn,
    SchemaModelEntry,
    SchemaSeedEntry,
    SettingsConfig,
    SourceEntry,
)


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
    upstream_seed_file_path: Path | None = None,
    upstream_seed_name: str = "order_statuses",
) -> ProjectGraph:
    function: CompiledFunction = CompiledFunction(
        key=CompiledObjectKey(resource_type=CompiledResourceType.UDF, name="normalize_order"),
        deps=(),
        name="normalize_order",
        relative_path=Path("functions/sql/normalize_order.sql"),
        arguments=(FunctionArgument(name="value", type="INTEGER"),),
        returns="INTEGER",
        body_sql=function_body_sql,
        destination=CompiledRelationLocation(
            database=None,
            schema="staging",
            name="normalize_order",
            qualified_name="staging.normalize_order",
        ),
        fingerprint_destination=CompiledRelationLocation(
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
    upstream_config_values.update(upstream_extra_config or {})
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
    seed: CompiledSeed | None
    seed_key: CompiledObjectKey | None
    seed, seed_key = _VIRTUAL_SEED_BUILDERS[upstream_seed_file_path is not None](
        upstream_seed_file_path, upstream_seed_name
    )
    upstream_model_deps: tuple[CompiledObjectKey, ...] = cast(
        tuple[CompiledObjectKey, ...],
        ((upstream_source.key,), (upstream_source.key, seed_key))[seed_key is not None],
    )
    upstream_model: CompiledModel = CompiledModel(
        key=CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name=upstream_model_name),
        deps=upstream_model_deps,
        name=upstream_model_name,
        relative_path=Path(f"models/{upstream_model_name}.sql"),
        query_sql=upstream_query_sql,
        config=CompileModelConfig(values=upstream_config_values),
        schema_entry=(
            None,
            SchemaModelEntry(name=upstream_model_name, columns=upstream_schema_columns),
        )[bool(upstream_schema_columns)],
        destination=CompiledRelationLocation(
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
        destination=CompiledRelationLocation(
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
        destination=CompiledRelationLocation(
            database=None,
            schema="marts",
            name="dim_customers",
            qualified_name="marts.dim_customers",
        ),
    )
    downstream_deps: tuple[CompiledObjectKey, ...] = (
        (upstream_model.key, function.key),
        (upstream_model.key, function.key, unrelated_model.key),
    )[downstream_depends_on_dim_customers]
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
        seeds=cast(tuple[CompiledSeed, ...], ((), (seed,))[seed is not None]),
        functions=(function,),
    )
    upstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = (
        build_execution_upstream_deps(project)
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
    _VIRTUAL_SEED_KEY_ADDERS[seed is not None](all_keys, seed)
    return ProjectGraph(
        project=project,
        upstream_deps=upstream_deps,
        downstream_deps=downstream_deps,
        tag_index={},
        path_index={},
        all_keys=all_keys,
    )


def _build_virtual_seed(
    seed_file_path: Path | None, seed_name: str
) -> tuple[CompiledSeed | None, CompiledObjectKey | None]:
    resolved_seed_file_path: Path = cast(Path, seed_file_path)
    seed_key: CompiledObjectKey = CompiledObjectKey(
        resource_type=CompiledResourceType.SEED,
        name=seed_name,
    )
    seed_schema_entry: SchemaSeedEntry = SchemaSeedEntry(
        name=seed_name,
        columns=(SchemaColumn(name="status"),),
    )
    seed_schema_file: DiscoveredSchemaFile = DiscoveredSchemaFile(
        file_path=Path("seeds/schema.yml"),
        relative_path=Path("seeds/schema.yml"),
        contents="",
        model_entries=(),
        seed_entries=(seed_schema_entry,),
    )
    seed: CompiledSeed = CompiledSeed(
        key=seed_key,
        deps=(),
        name=seed_name,
        seed_file=DiscoveredSeedFile(
            file_path=resolved_seed_file_path,
            relative_path=Path("seeds") / resolved_seed_file_path.name,
        ),
        schema_entry=seed_schema_entry,
        schema_file=seed_schema_file,
        destination=CompiledRelationLocation(
            database=None,
            schema="staging",
            name=seed_name,
            qualified_name=f"staging.{seed_name}",
        ),
    )
    return seed, seed_key


def _build_no_virtual_seed(
    seed_file_path: Path | None, seed_name: str
) -> tuple[CompiledSeed | None, CompiledObjectKey | None]:
    del seed_file_path, seed_name
    return None, None


def _add_virtual_seed_key(
    all_keys: dict[str, CompiledObjectKey], seed: CompiledSeed | None
) -> None:
    resolved_seed: CompiledSeed = cast(CompiledSeed, seed)
    all_keys[resolved_seed.name] = resolved_seed.key


def _skip_virtual_seed_key(
    all_keys: dict[str, CompiledObjectKey], seed: CompiledSeed | None
) -> None:
    del all_keys, seed


_VIRTUAL_SEED_BUILDERS: MappingProxyType[
    bool,
    Callable[[Path | None, str], tuple[CompiledSeed | None, CompiledObjectKey | None]],
] = MappingProxyType({False: _build_no_virtual_seed, True: _build_virtual_seed})
_VIRTUAL_SEED_KEY_ADDERS: MappingProxyType[
    bool, Callable[[dict[str, CompiledObjectKey], CompiledSeed | None], None]
] = MappingProxyType({False: _skip_virtual_seed_key, True: _add_virtual_seed_key})
