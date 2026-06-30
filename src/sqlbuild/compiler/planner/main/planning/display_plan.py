"""Display-only planner helpers for external plan surfaces."""

from __future__ import annotations

from sqlbuild.compiler.compile.models.core import (
    CompiledObjectKey,
    CompiledProject,
)
from sqlbuild.compiler.planner.helpers.graph.core import build_downstream_deps, build_upstream_deps
from sqlbuild.compiler.planner.helpers.output.strategy import get_materialization_type
from sqlbuild.compiler.planner.models import BackfillResult, ModelPlanEntry, PlanOutput
from sqlbuild.compiler.planner.types import (
    BackfillAction,
    MaterializationType,
    PlanAction,
    PlanReason,
)


def build_display_only_sqlbuild_plan(
    *, project: CompiledProject, selected_model_names: tuple[str, ...], full_refresh: bool
) -> PlanOutput:
    """Build a display-only plan when warehouse planning cannot fully resolve."""

    selected_names: frozenset[str] = frozenset(selected_model_names)
    model_entries: list[ModelPlanEntry] = []
    for model in project.models:
        if model.name not in selected_names:
            continue
        materialization_type: MaterializationType = get_materialization_type(model)
        model_entries.append(
            ModelPlanEntry(
                key=model.key,
                name=model.name,
                relative_path=model.relative_path,
                materialization_type=materialization_type,
                action=_display_action(materialization_type),
                reason=PlanReason.FULL_REFRESH if full_refresh else PlanReason.NO_CHANGE,
                destination=model.destination,
                fingerprint_query_sql=model.query_sql,
                resolved_sql=model.query_sql,
                logical_ddl="",
                incremental_strategy=_as_optional_string(
                    model.config.values.get("incremental_strategy")
                ),
                incremental_mode=_as_optional_string(model.config.values.get("incremental_mode")),
                cursor_column=_as_optional_string(model.config.values.get("cursor_column")),
                cursor_type=_as_optional_string(model.config.values.get("cursor_type")),
                backfill=BackfillResult(action=BackfillAction.FORWARD_ONLY),
                custom_materialization_name=(
                    _as_optional_string(model.config.values.get("materialized"))
                    if materialization_type == MaterializationType.CUSTOM
                    else None
                ),
            )
        )
    upstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = build_upstream_deps(
        project
    )
    return PlanOutput(
        execution_order=tuple(entry.key for entry in model_entries),
        model_entries=tuple(model_entries),
        selected_keys=frozenset(entry.key for entry in model_entries),
        upstream_deps=upstream_deps,
        downstream_deps=build_downstream_deps(upstream_deps),
    )


def _display_action(materialization_type: MaterializationType) -> PlanAction:
    if materialization_type == MaterializationType.VIEW:
        return PlanAction.CREATE_VIEW
    if materialization_type == MaterializationType.INCREMENTAL:
        return PlanAction.INCREMENTAL_APPEND
    if materialization_type == MaterializationType.CUSTOM:
        return PlanAction.CUSTOM
    return PlanAction.CREATE_TABLE


def _as_optional_string(value: object) -> str | None:
    return value if isinstance(value, str) else None
