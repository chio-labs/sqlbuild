"""Public virtual planner output entrypoint."""

from __future__ import annotations

from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.virtual.planner.helpers.output import (
    rewrite_virtual_plan_entries,
    with_virtual_metadata,
)
from sqlbuild.virtual.planner.models import VirtualPlanSemantics


def apply_virtual_plan_output(
    *,
    plan_output: PlanOutput,
    target_name: str,
    semantics: VirtualPlanSemantics,
    selected_model_names: tuple[str, ...] = (),
) -> PlanOutput:
    """Rewrite plan entries and attach virtual environment metadata."""

    rewritten: PlanOutput = rewrite_virtual_plan_entries(
        plan_output=plan_output,
        stale_root_reasons=semantics.stale_root_reasons,
        stale_root_causes=semantics.stale_root_causes,
        stale_root_cause_reasons=semantics.stale_root_cause_reasons,
        previous_query_sqls=semantics.bound_previous_query_sqls,
        run_despite_unchanged=semantics.run_despite_unchanged,
    )
    return with_virtual_metadata(
        plan_output=rewritten,
        target_name=target_name,
        stale_model_names=semantics.stale_model_names,
        stale_root_names=tuple(sorted(semantics.stale_root_reasons)),
        remaining_stale_model_names=tuple(
            sorted(set(semantics.stale_model_names) - set(selected_model_names))
        ),
        source_freshness_observed_source_names=(semantics.source_freshness_observed_source_names),
        source_freshness_incomplete_source_names=(
            semantics.source_freshness_incomplete_source_names
        ),
        source_freshness_incomplete_model_names=(semantics.source_freshness_incomplete_model_names),
    )
