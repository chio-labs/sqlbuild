"""Public clone planning entrypoints."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.planner._helpers.reuse.clone import (
    build_clone_function_entries,
    build_clone_model_entries,
    build_clone_plan_output,
    build_clone_seed_entries,
    build_clone_source_entries,
    build_origin_model_entries,
    build_origin_seed_entries,
    build_origin_source_entries,
)
from sqlbuild.compiler.planner.models import (
    CloneSourcePlanEntry,
    FunctionPlanEntry,
    ModelPlanEntry,
    PlanOutput,
    SeedPlanEntry,
)


def run_clone_planning(
    *,
    project: CompiledProject,
    select: tuple[str, ...],
    exclude: tuple[str, ...],
    adapter: BaseAdapter,
    connection: Any,
    origin_project: CompiledProject,
    origin_source_project: CompiledProject,
    destination_source_project: CompiledProject,
) -> tuple[
    PlanOutput,
    tuple[CloneSourcePlanEntry, ...],
    tuple[ModelPlanEntry, ...],
    tuple[SeedPlanEntry, ...],
    tuple[FunctionPlanEntry, ...],
    tuple[ModelPlanEntry, ...],
    tuple[SeedPlanEntry, ...],
    tuple[CloneSourcePlanEntry, ...],
]:
    """Prepare planner outputs needed for clone execution."""

    clone_plan: PlanOutput = build_clone_plan_output(
        project=project,
        select=select,
        exclude=exclude,
    )
    destination_model_entries: tuple[ModelPlanEntry, ...] = build_clone_model_entries(
        project=project,
        plan=clone_plan,
        adapter=adapter,
        connection=connection,
        source_project=destination_source_project,
    )
    destination_seed_entries: tuple[SeedPlanEntry, ...] = build_clone_seed_entries(
        project=project,
        plan=clone_plan,
    )
    destination_function_entries: tuple[FunctionPlanEntry, ...] = build_clone_function_entries(
        project=project,
        plan=clone_plan,
        adapter=adapter,
        connection=connection,
        source_project=destination_source_project,
    )
    destination_source_entries: tuple[CloneSourcePlanEntry, ...] = ()
    if destination_source_project.effective_target_name == project.effective_target_name:
        destination_source_entries = build_clone_source_entries(
            project=project,
            plan=clone_plan,
            adapter=adapter,
        )
    origin_model_entries: tuple[ModelPlanEntry, ...] = build_origin_model_entries(
        project=origin_project,
        selected_names=frozenset(entry.name for entry in destination_model_entries),
    )
    origin_seed_entries: tuple[SeedPlanEntry, ...] = build_origin_seed_entries(
        project=origin_project,
        selected_names=frozenset(entry.name for entry in destination_seed_entries),
    )
    origin_source_entries: tuple[CloneSourcePlanEntry, ...] = build_origin_source_entries(
        project=origin_source_project,
        selected_names=frozenset(entry.name for entry in destination_source_entries),
        adapter=adapter,
    )
    origin_source_entries_by_name: dict[str, CloneSourcePlanEntry] = {
        entry.name: entry for entry in origin_source_entries
    }
    destination_source_entries = tuple(
        entry
        for entry in destination_source_entries
        if (origin_entry := origin_source_entries_by_name.get(entry.name)) is not None
        and origin_entry.destination != entry.destination
    )
    origin_source_entries = tuple(
        origin_source_entries_by_name[entry.name] for entry in destination_source_entries
    )
    return (
        clone_plan,
        destination_source_entries,
        destination_model_entries,
        destination_seed_entries,
        destination_function_entries,
        origin_model_entries,
        origin_seed_entries,
        origin_source_entries,
    )
