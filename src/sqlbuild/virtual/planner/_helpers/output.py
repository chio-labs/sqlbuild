"""Virtual planner output post-processing helpers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.planner.main.execution.execution import build_execution_plan
from sqlbuild.compiler.planner.models import (
    CascadeResult,
    DeferralInputs,
    FunctionPlanEntry,
    ModelPlanEntry,
    PlannerOverrides,
    PlannerPolicies,
    PlannerSelection,
    PlanOutput,
    RunDespiteUnchangedDecision,
    RunDespiteUnchangedPlanningResult,
    SeedPlanEntry,
)
from sqlbuild.compiler.planner.types import BackfillAction, PlanReason
from sqlbuild.virtual.planner.models import (
    VirtualBoundState,
    VirtualPlanOptions,
    VirtualPlanSemantics,
)


def rewrite_virtual_plan_entries(
    *,
    plan_output: PlanOutput,
    stale_root_reasons: dict[str, PlanReason],
    stale_root_causes: dict[str, str],
    stale_root_cause_reasons: dict[str, PlanReason] | None = None,
    previous_query_sqls: dict[str, str] | None = None,
    current_metadata_jsons: dict[str, str] | None = None,
    previous_metadata_jsons: dict[str, str] | None = None,
    previous_function_query_sqls: dict[str, str] | None = None,
    run_despite_unchanged: RunDespiteUnchangedPlanningResult | None = None,
    seed_plan_reasons: dict[str, PlanReason] | None = None,
) -> PlanOutput:
    """Rewrite standard planner entries with virtual-specific reasons and causes."""

    rewritten_entries: list[ModelPlanEntry] = []
    cause_reasons: dict[str, PlanReason] = stale_root_cause_reasons or stale_root_reasons
    entry: ModelPlanEntry
    for entry in plan_output.model_entries:
        run_decision: RunDespiteUnchangedDecision | None = (
            run_despite_unchanged.decisions.get(entry.name)
            if run_despite_unchanged is not None
            else None
        )
        if entry.name in stale_root_reasons:
            rewritten_entries.append(
                replace(
                    entry,
                    reason=stale_root_reasons[entry.name],
                    cascade=None,
                    run_despite_unchanged=run_decision,
                    previous_query_sql=(previous_query_sqls or {}).get(
                        entry.name,
                        entry.previous_query_sql,
                    ),
                    fingerprint_metadata_json=(current_metadata_jsons or {}).get(entry.name),
                    previous_metadata_json=(previous_metadata_jsons or {}).get(entry.name),
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
                        effective_action=BackfillAction.FORWARD_ONLY,
                        effective_duration=None,
                        root_cause=root_cause,
                        root_reason=cause_reasons[root_cause],
                        causes=(),
                    ),
                )
            )
            continue
        rewritten_entries.append(entry)
    rewritten_function_entries: list[FunctionPlanEntry] = []
    function_entry: FunctionPlanEntry
    for function_entry in plan_output.function_entries:
        previous_function_query_sql: str | None = (previous_function_query_sqls or {}).get(
            function_entry.name,
            function_entry.previous_query_sql,
        )
        if previous_function_query_sql is not None:
            rewritten_function_entries.append(
                replace(
                    function_entry,
                    previous_query_sql=previous_function_query_sql,
                    reason=(
                        PlanReason.QUERY_CHANGED
                        if previous_function_query_sql != function_entry.fingerprint_query_sql
                        else function_entry.reason
                    ),
                )
            )
            continue
        rewritten_function_entries.append(function_entry)
    rewritten_seed_entries: list[SeedPlanEntry] = []
    seed_entry: SeedPlanEntry
    for seed_entry in plan_output.seed_entries:
        seed_reason: PlanReason | None = (seed_plan_reasons or {}).get(seed_entry.name)
        if seed_reason is None:
            rewritten_seed_entries.append(seed_entry)
            continue
        rewritten_seed_entries.append(replace(seed_entry, reason=seed_reason))
    return replace(
        plan_output,
        model_entries=tuple(rewritten_entries),
        function_entries=tuple(rewritten_function_entries),
        seed_entries=tuple(rewritten_seed_entries),
    )


def with_virtual_metadata(
    *,
    plan_output: PlanOutput,
    target_name: str | None,
    stale_model_names: tuple[str, ...],
    stale_root_names: tuple[str, ...],
    remaining_stale_model_names: tuple[str, ...] = (),
    source_freshness_observed_source_names: tuple[str, ...] = (),
    source_freshness_unchanged_source_names: tuple[str, ...] = (),
    source_freshness_incomplete_source_names: tuple[str, ...] = (),
    source_freshness_incomplete_model_names: tuple[str, ...] = (),
) -> PlanOutput:
    """Attach virtual-specific metadata to a plan output."""

    metadata: dict[str, object] = dict(plan_output.metadata)
    metadata.update(
        {
            "virtual_mode": True,
            "virtual_environment_name": target_name,
            "virtual_environment_status": "finalized" if not stale_model_names else "working",
            "virtual_stale_model_names": stale_model_names,
            "virtual_stale_root_names": stale_root_names,
            "virtual_remaining_stale_model_names": remaining_stale_model_names,
            "virtual_source_freshness_observed_source_names": (
                source_freshness_observed_source_names
            ),
            "virtual_source_freshness_unchanged_source_names": (
                source_freshness_unchanged_source_names
            ),
            "virtual_source_freshness_incomplete_source_names": (
                source_freshness_incomplete_source_names
            ),
            "virtual_source_freshness_incomplete_model_names": (
                source_freshness_incomplete_model_names
            ),
        }
    )
    return replace(plan_output, metadata=metadata)


def build_virtual_plan_output(
    *,
    graph: ProjectGraph,
    adapter: BaseAdapter,
    connection: Any,
    effective_select_with_seeds: tuple[str, ...],
    options: VirtualPlanOptions,
    bound: VirtualBoundState,
    discovered_inputs: DiscoveredProjectInputs,
    on_progress: Callable[[str], None] | None,
) -> PlanOutput:
    """Build the execution plan for the selection, or an empty structural plan."""

    if not effective_select_with_seeds:
        return PlanOutput(
            execution_order=tuple(graph.upstream_deps),
            upstream_deps=graph.upstream_deps,
            downstream_deps=graph.downstream_deps,
            model_locations={model.name: model.destination for model in graph.project.models},
            function_locations={
                function.name: function.destination for function in graph.project.functions
            },
            seed_locations={seed.name: seed.destination for seed in graph.project.seeds},
            source_map={source.name: source.source_entry for source in graph.project.sources},
        )
    return build_execution_plan(
        project=graph.project,
        adapter=adapter,
        connection=connection,
        selection=PlannerSelection(select=effective_select_with_seeds),
        overrides=PlannerOverrides(
            cursor_overrides=options.cursor_overrides,
            full_refresh=options.full_refresh,
            reload_sources=options.reload_sources,
        ),
        deferral=DeferralInputs(
            deferred_locations=bound.deferred_locations,
            deferred_relations=bound.deferred_relations,
            defer_sources_to=options.defer_sources_to,
            source_deferral_enabled=options.source_deferral_enabled,
        ),
        policies=PlannerPolicies(
            auto_load_sources=options.auto_load_sources,
            enable_reuse_planning=False,
        ),
        on_progress=on_progress,
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
    )


def attach_virtual_plan_metadata(
    *,
    plan_output: PlanOutput,
    graph: ProjectGraph,
    semantics: VirtualPlanSemantics,
    bound: VirtualBoundState,
    target_name: str | None,
    effective_select: tuple[str, ...],
) -> PlanOutput:
    """Attach virtual staleness and freshness metadata to a plan output."""

    return with_virtual_metadata(
        plan_output=plan_output,
        target_name=target_name,
        stale_model_names=semantics.stale_model_names,
        stale_root_names=tuple(sorted(semantics.stale_root_reasons)),
        remaining_stale_model_names=tuple(
            sorted(set(semantics.stale_model_names) - set(effective_select))
        ),
        source_freshness_observed_source_names=(semantics.source_freshness_observed_source_names),
        source_freshness_unchanged_source_names=(bound.source_freshness_unchanged_source_names),
        source_freshness_incomplete_source_names=(
            semantics.source_freshness_incomplete_source_names
        ),
        source_freshness_incomplete_model_names=(semantics.source_freshness_incomplete_model_names),
    )
