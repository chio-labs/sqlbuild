"""Per-model action resolution from each model's own change."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.models import (
    ChangeDetectionResult,
    PlannerChangeResults,
    PlannerResolvedActions,
    PlannerScope,
    ResolvedModelAction,
)


def resolve_model_actions(
    *,
    scope: PlannerScope,
    changes: PlannerChangeResults,
) -> PlannerResolvedActions:
    """Resolve each selected model's backfill from its own change and replay_on_change only."""

    resolved: dict[str, ResolvedModelAction] = {}
    key: CompiledObjectKey
    for key in scope.execution_order:
        if key not in scope.selected_keys or key.resource_type != CompiledResourceType.MODEL:
            continue
        change: ChangeDetectionResult | None = changes.models.get(key.name)
        if key.name not in scope.models_by_name or change is None:
            continue
        resolved[key.name] = ResolvedModelAction(change=change, backfill=change.backfill)
    return PlannerResolvedActions(models=resolved)
