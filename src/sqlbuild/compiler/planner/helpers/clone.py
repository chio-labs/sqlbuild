"""Clone planner helper functions."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models import (
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationTarget,
)
from sqlbuild.compiler.planner.helpers.graph import (
    build_downstream_deps,
    build_upstream_deps,
    topologically_order_keys,
)
from sqlbuild.compiler.planner.helpers.plan_entry import (
    build_path_index,
    build_tag_index,
    gather_source_columns,
)
from sqlbuild.compiler.planner.helpers.resolve.refs import (
    build_model_targets,
    build_seed_targets,
)
from sqlbuild.compiler.planner.helpers.resolve.resolve import resolve_model_sql
from sqlbuild.compiler.planner.helpers.selectors import resolve_selectors
from sqlbuild.compiler.planner.helpers.strategy import get_materialization_type
from sqlbuild.compiler.planner.models import (
    BackfillResult,
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
from sqlbuild.spec.models.source import SourceEntry


def build_clone_plan_output(
    *,
    project: CompiledProject,
    select: tuple[str, ...],
    exclude: tuple[str, ...],
) -> PlanOutput:
    upstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = build_upstream_deps(
        project
    )
    downstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = build_downstream_deps(
        upstream_deps
    )
    all_keys: dict[str, CompiledObjectKey] = {
        **{model.name: model.key for model in project.models},
        **{source.name: source.key for source in project.sources},
        **{seed.name: seed.key for seed in project.seeds},
    }
    selected_keys: frozenset[CompiledObjectKey] = resolve_selectors(
        select=select,
        exclude=exclude,
        all_keys=all_keys,
        upstream=upstream_deps,
        downstream=downstream_deps,
        tag_index=build_tag_index(project),
        path_index=build_path_index(project),
    )
    return PlanOutput(
        execution_order=topologically_order_keys(upstream_deps),
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
) -> tuple[ModelPlanEntry, ...]:
    model_targets: dict[str, CompiledRelationTarget] = build_model_targets(project.models)
    seed_targets: dict[str, CompiledRelationTarget] = build_seed_targets(project.seeds)
    source_map: dict[str, SourceEntry] = {
        source.name: source.source_entry for source in project.sources
    }
    source_warehouse_columns: dict[str, tuple[Any, ...]] = gather_source_columns(
        project=project,
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
                model=model,
                snapshot=WarehouseSnapshot(),
                model_targets=model_targets,
                seed_targets=seed_targets,
                source_map=source_map,
                source_warehouse_columns=source_warehouse_columns,
                star_exclude_keyword=adapter.star_exclude_keyword(),
                backfill=BackfillResult(action=BackfillAction.WARN_ONLY),
                full_refresh=False,
                start_cursor_override=None,
                end_cursor_override=None,
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
            target=model.target,
            fingerprint_query_sql="",
            resolved_sql=resolved_sql,
            logical_ddl="",
        )
    return tuple(entries_by_key[key] for key in plan.execution_order if key in entries_by_key)


def build_source_model_entries(
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
                target=model.target,
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
            target=seed.target,
            file_path=seed.seed_file.file_path,
            columns=tuple(),
        )
        for seed in project.seeds
        if seed.key in plan.selected_keys
    )


def build_source_seed_entries(
    *,
    project: CompiledProject,
    selected_names: frozenset[str],
) -> tuple[SeedPlanEntry, ...]:
    return tuple(
        SeedPlanEntry(
            key=seed.key,
            name=seed.name,
            target=seed.target,
            file_path=seed.seed_file.file_path,
            columns=tuple(),
        )
        for seed in project.seeds
        if seed.name in selected_names
    )


def is_disabled(model: CompiledModel) -> bool:
    raw: object | None = model.config.values.get("enabled")
    return isinstance(raw, bool) and not raw
