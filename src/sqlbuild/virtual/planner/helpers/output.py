"""Virtual planner output post-processing helpers."""

from __future__ import annotations

from dataclasses import replace

from sqlbuild.compiler.planner.models import CascadeResult, ModelPlanEntry, PlanOutput
from sqlbuild.compiler.planner.types import BackfillAction, PlanReason


def rewrite_virtual_plan_entries(
    *,
    plan_output: PlanOutput,
    stale_root_reasons: dict[str, PlanReason],
    stale_root_causes: dict[str, str],
) -> PlanOutput:
    """Rewrite direct planner entries with virtual-specific reasons and causes."""

    rewritten_entries: list[ModelPlanEntry] = []
    entry: ModelPlanEntry
    for entry in plan_output.model_entries:
        if entry.name in stale_root_reasons:
            rewritten_entries.append(
                replace(
                    entry,
                    reason=stale_root_reasons[entry.name],
                    cascade=None,
                )
            )
            continue
        root_cause: str | None = stale_root_causes.get(entry.name)
        if root_cause is not None:
            rewritten_entries.append(
                replace(
                    entry,
                    reason=PlanReason.NO_CHANGE,
                    cascade=CascadeResult(
                        effective_action=BackfillAction.WARN_ONLY,
                        effective_duration=None,
                        root_cause=root_cause,
                        root_reason=stale_root_reasons[root_cause],
                        causes=(),
                    ),
                )
            )
            continue
        rewritten_entries.append(entry)
    return replace(plan_output, model_entries=tuple(rewritten_entries))


def with_virtual_metadata(
    *,
    plan_output: PlanOutput,
    environment_name: str | None,
    stale_model_names: tuple[str, ...],
    stale_root_names: tuple[str, ...],
) -> PlanOutput:
    """Attach virtual-specific metadata to a plan output."""

    metadata: dict[str, object] = dict(plan_output.metadata)
    metadata.update(
        {
            "virtual_mode": True,
            "virtual_environment_name": environment_name,
            "virtual_environment_status": "finalized" if not stale_model_names else "working",
            "virtual_stale_model_names": stale_model_names,
            "virtual_stale_root_names": stale_root_names,
        }
    )
    return replace(plan_output, metadata=metadata)
