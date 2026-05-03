"""Public clone planning entrypoints."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.planner.helpers.clone import (
    build_clone_model_entries,
    build_clone_plan_output,
    build_clone_seed_entries,
    build_source_model_entries,
    build_source_seed_entries,
)
from sqlbuild.compiler.planner.models import ModelPlanEntry, PlanOutput, SeedPlanEntry


def run_clone_planning(
    *,
    project: CompiledProject,
    select: tuple[str, ...],
    exclude: tuple[str, ...],
    adapter: BaseAdapter,
    connection: Any,
    source_project: CompiledProject,
) -> tuple[
    PlanOutput,
    tuple[ModelPlanEntry, ...],
    tuple[SeedPlanEntry, ...],
    tuple[ModelPlanEntry, ...],
    tuple[SeedPlanEntry, ...],
]:
    """Prepare planner outputs needed for clone execution."""

    clone_plan: PlanOutput = build_clone_plan_output(
        project=project,
        select=select,
        exclude=exclude,
    )
    target_model_entries: tuple[ModelPlanEntry, ...] = build_clone_model_entries(
        project=project,
        plan=clone_plan,
        adapter=adapter,
        connection=connection,
    )
    target_seed_entries: tuple[SeedPlanEntry, ...] = build_clone_seed_entries(
        project=project,
        plan=clone_plan,
    )
    source_model_entries: tuple[ModelPlanEntry, ...] = build_source_model_entries(
        project=source_project,
        selected_names=frozenset(entry.name for entry in target_model_entries),
    )
    source_seed_entries: tuple[SeedPlanEntry, ...] = build_source_seed_entries(
        project=source_project,
        selected_names=frozenset(entry.name for entry in target_seed_entries),
    )
    return (
        clone_plan,
        target_model_entries,
        target_seed_entries,
        source_model_entries,
        source_seed_entries,
    )
