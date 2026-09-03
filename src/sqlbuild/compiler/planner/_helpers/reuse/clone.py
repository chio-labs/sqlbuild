"""Clone planner helper functions."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models import (
    CompiledFunction,
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationLocation,
    CompiledSource,
)
from sqlbuild.compiler.graph.main._build_lineage_downstream_deps import (
    build_lineage_downstream_deps,
)
from sqlbuild.compiler.graph.main._build_lineage_upstream_deps import (
    build_lineage_upstream_deps,
)
from sqlbuild.compiler.planner._helpers.graph.core import (
    build_downstream_deps,
    build_execution_upstream_deps,
    topologically_order_keys,
)
from sqlbuild.compiler.planner._helpers.graph.selector_indexes import (
    build_model_path_index_impl as build_model_path_index,
)
from sqlbuild.compiler.planner._helpers.graph.selector_indexes import (
    build_model_tag_index_impl as build_model_tag_index,
)
from sqlbuild.compiler.planner._helpers.graph.selectors import resolve_selectors
from sqlbuild.compiler.planner._helpers.identity.functions import (
    build_compiled_function_fingerprint_sql,
)
from sqlbuild.compiler.planner._helpers.output.plan_entry import (
    gather_source_columns,
)
from sqlbuild.compiler.planner._helpers.output.strategy import get_materialization_type
from sqlbuild.compiler.planner._helpers.resolve.refs import (
    build_function_locations,
    build_model_locations,
    build_seed_locations,
)
from sqlbuild.compiler.planner._helpers.resolve.resolve import (
    resolve_function_sql,
    resolve_model_sql,
)
from sqlbuild.compiler.planner.models import (
    BackfillResult,
    CloneSourcePlanEntry,
    CursorOverridePair,
    FunctionPlanEntry,
    ModelPlanContext,
    ModelPlanEntry,
    PlanOutput,
    SeedPlanEntry,
    WarehouseSnapshot,
)
from sqlbuild.compiler.planner.types import (
    BackfillAction,
    MaterializationType,
    PlanAction,
    PlanReason,
)
from sqlbuild.spec.contracts.models import SourceEntry


def build_clone_plan_output(
    *,
    project: CompiledProject,
    select: tuple[str, ...],
    exclude: tuple[str, ...],
) -> PlanOutput:
    upstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = (
        build_execution_upstream_deps(project)
    )
    downstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = build_downstream_deps(
        upstream_deps
    )
    all_keys: dict[str, CompiledObjectKey] = {
        **{model.name: model.key for model in project.models},
        **{source.name: source.key for source in project.sources},
        **{seed.name: seed.key for seed in project.seeds},
        **{function.name: function.key for function in project.functions},
    }
    lineage_upstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = (
        build_lineage_upstream_deps(project)
    )
    selected_keys: frozenset[CompiledObjectKey] = resolve_selectors(
        select=select,
        exclude=exclude,
        all_keys=all_keys,
        upstream=lineage_upstream,
        downstream=build_lineage_downstream_deps(lineage_upstream),
        tag_index=build_model_tag_index(project),
        path_index=build_model_path_index(project),
    )
    return PlanOutput(
        execution_order=topologically_order_keys(upstream=upstream_deps),
        selected_keys=selected_keys,
        upstream_deps=upstream_deps,
        downstream_deps=downstream_deps,
    )


def build_clone_model_entries(
    *,
    project: CompiledProject,
    plan: PlanOutput,
    adapter: BaseAdapter,
    connection: Any,
    source_project: CompiledProject | None = None,
) -> tuple[ModelPlanEntry, ...]:
    effective_source_project: CompiledProject = source_project or project
    model_locations: dict[str, CompiledRelationLocation] = build_model_locations(project.models)
    seed_locations: dict[str, CompiledRelationLocation] = build_seed_locations(project.seeds)
    function_locations: dict[str, CompiledRelationLocation] = build_function_locations(
        project.functions
    )
    source_map: dict[str, SourceEntry] = {
        source.name: source.source_entry for source in effective_source_project.sources
    }
    source_warehouse_columns: dict[str, tuple[Any, ...]] = gather_source_columns(
        project=effective_source_project,
        adapter=adapter,
        connection=connection,
    )
    entries_by_key: dict[CompiledObjectKey, ModelPlanEntry] = {}
    model: CompiledModel
    for model in project.models:
        if model.key not in plan.selected_keys or is_disabled(model):
            continue
        materialization_type: MaterializationType = get_materialization_type(model)
        resolved_sql: str = ""
        if materialization_type == MaterializationType.VIEW:
            resolved_sql = resolve_model_sql(
                adapter=adapter,
                model=model,
                snapshot=WarehouseSnapshot(),
                context=ModelPlanContext(
                    model_locations=model_locations,
                    models_by_name={},
                    functions_by_name={function.name: function for function in project.functions},
                    seed_locations=seed_locations,
                    function_locations=function_locations,
                    source_map=source_map,
                    source_warehouse_columns=source_warehouse_columns,
                    star_exclude_keyword=adapter.star_exclude_keyword(),
                ),
                backfill=BackfillResult(action=BackfillAction.FORWARD_ONLY),
                full_refresh=False,
                cursor_overrides=CursorOverridePair(),
            )
        entries_by_key[model.key] = ModelPlanEntry(
            key=model.key,
            name=model.name,
            relative_path=model.relative_path,
            materialization_type=materialization_type,
            action=(
                PlanAction.CREATE_VIEW
                if materialization_type == MaterializationType.VIEW
                else PlanAction.CREATE_TABLE
            ),
            reason=PlanReason.NO_CHANGE,
            destination=model.destination,
            fingerprint_query_sql="",
            resolved_sql=resolved_sql,
            logical_ddl="",
        )
    return tuple(entries_by_key[key] for key in plan.execution_order if key in entries_by_key)


def build_clone_source_entries(
    *,
    project: CompiledProject,
    plan: PlanOutput,
    adapter: BaseAdapter,
) -> tuple[CloneSourcePlanEntry, ...]:
    entries_by_key: dict[CompiledObjectKey, CloneSourcePlanEntry] = {}
    source: CompiledSource
    for source in project.sources:
        source_entry: SourceEntry = source.source_entry
        if (
            source.key not in plan.selected_keys
            or not source_entry.managed
            or source_entry.loader is None
            or source_entry.expression is not None
        ):
            continue
        relation_name: str = source_entry.table or source_entry.name
        entries_by_key[source.key] = CloneSourcePlanEntry(
            key=source.key,
            name=source.name,
            destination=CompiledRelationLocation(
                database=source_entry.database,
                schema=source_entry.schema,
                name=relation_name,
                qualified_name=adapter.render_qualified_name(
                    database=source_entry.database,
                    schema=source_entry.schema,
                    name=relation_name,
                ),
            ),
        )
    return tuple(entries_by_key[key] for key in plan.execution_order if key in entries_by_key)


def build_clone_function_entries(
    *,
    project: CompiledProject,
    plan: PlanOutput,
    adapter: BaseAdapter,
    connection: Any,
    source_project: CompiledProject | None = None,
) -> tuple[FunctionPlanEntry, ...]:
    """Build destination-resolved function definitions for clone recreation."""
    effective_source_project: CompiledProject = source_project or project
    model_locations: dict[str, CompiledRelationLocation] = build_model_locations(project.models)
    seed_locations: dict[str, CompiledRelationLocation] = build_seed_locations(project.seeds)
    function_locations: dict[str, CompiledRelationLocation] = build_function_locations(
        project.functions
    )
    source_map: dict[str, SourceEntry] = {
        source.name: source.source_entry for source in effective_source_project.sources
    }
    source_warehouse_columns: dict[str, tuple[Any, ...]] = gather_source_columns(
        project=effective_source_project,
        adapter=adapter,
        connection=connection,
    )
    entries_by_key: dict[CompiledObjectKey, FunctionPlanEntry] = {}
    function: CompiledFunction
    for function in project.functions:
        if function.key not in plan.selected_keys:
            continue
        entries_by_key[function.key] = FunctionPlanEntry(
            key=function.key,
            name=function.name,
            relative_path=function.relative_path,
            destination=function.destination,
            arguments=function.arguments,
            returns=function.returns,
            body_sql=resolve_function_sql(
                adapter=adapter,
                function=function,
                model_locations=model_locations,
                seed_locations=seed_locations,
                function_locations=function_locations,
                source_map=source_map,
                source_warehouse_columns=source_warehouse_columns,
                star_exclude_keyword=adapter.star_exclude_keyword(),
            ),
            fingerprint_query_sql=build_compiled_function_fingerprint_sql(function),
            fingerprint_destination=function.fingerprint_destination,
            return_columns=function.return_columns,
            language=function.language,
            source_file_path=function.source_file_path,
            runtime_version=function.runtime_version,
            entry_point=function.entry_point,
            packages=function.packages,
        )
    return tuple(entries_by_key[key] for key in plan.execution_order if key in entries_by_key)


def build_origin_source_entries(
    *,
    project: CompiledProject,
    selected_names: frozenset[str],
    adapter: BaseAdapter,
) -> tuple[CloneSourcePlanEntry, ...]:
    selected_keys: frozenset[CompiledObjectKey] = frozenset(
        source.key for source in project.sources if source.name in selected_names
    )
    return build_clone_source_entries(
        project=project,
        plan=PlanOutput(
            execution_order=tuple(source.key for source in project.sources),
            selected_keys=selected_keys,
        ),
        adapter=adapter,
    )


def build_origin_model_entries(
    *,
    project: CompiledProject,
    selected_names: frozenset[str],
) -> tuple[ModelPlanEntry, ...]:
    entries: list[ModelPlanEntry] = []
    model: CompiledModel
    for model in project.models:
        if model.name not in selected_names or is_disabled(model):
            continue
        materialization_type: MaterializationType = get_materialization_type(model)
        entries.append(
            ModelPlanEntry(
                key=model.key,
                name=model.name,
                relative_path=model.relative_path,
                materialization_type=materialization_type,
                action=(
                    PlanAction.CREATE_VIEW
                    if materialization_type == MaterializationType.VIEW
                    else PlanAction.CREATE_TABLE
                ),
                reason=PlanReason.NO_CHANGE,
                destination=model.destination,
                fingerprint_query_sql="",
                resolved_sql="",
                logical_ddl="",
            )
        )
    return tuple(entries)


def build_clone_seed_entries(
    *,
    project: CompiledProject,
    plan: PlanOutput,
) -> tuple[SeedPlanEntry, ...]:
    return tuple(
        SeedPlanEntry(
            key=seed.key,
            name=seed.name,
            destination=seed.destination,
            file_path=seed.seed_file.file_path,
            columns=tuple(),
            csv_settings=seed.schema_entry.csv_settings,
        )
        for seed in project.seeds
        if seed.key in plan.selected_keys
    )


def build_origin_seed_entries(
    *,
    project: CompiledProject,
    selected_names: frozenset[str],
) -> tuple[SeedPlanEntry, ...]:
    return tuple(
        SeedPlanEntry(
            key=seed.key,
            name=seed.name,
            destination=seed.destination,
            file_path=seed.seed_file.file_path,
            columns=tuple(),
            csv_settings=seed.schema_entry.csv_settings,
        )
        for seed in project.seeds
        if seed.name in selected_names
    )


def is_disabled(model: CompiledModel) -> bool:
    raw: object | None = model.config.values.get("enabled")
    return isinstance(raw, bool) and not raw
