"""Public clone planning entrypoints."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models.core import CompiledProject
from sqlbuild.compiler.planner.helpers.clone import (
    build_clone_model_entries,
    build_clone_plan_output,
    build_clone_seed_entries,
    build_origin_model_entries,
    build_origin_seed_entries,
)
from sqlbuild.compiler.planner.models import ModelPlanEntry, PlanOutput, SeedPlanEntry


def run_clone_planning(
    *,
    project: CompiledProject,
    select: tuple[str, ...],
    exclude: tuple[str, ...],
    adapter: BaseAdapter,
    connection: Any,
    origin_project: CompiledProject,
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
    destination_model_entries: tuple[ModelPlanEntry, ...] = build_clone_model_entries(
        project=project,
        plan=clone_plan,
        adapter=adapter,
        connection=connection,
    )
    destination_seed_entries: tuple[SeedPlanEntry, ...] = build_clone_seed_entries(
        project=project,
        plan=clone_plan,
    )
    origin_model_entries: tuple[ModelPlanEntry, ...] = build_origin_model_entries(
        project=origin_project,
        selected_names=frozenset(entry.name for entry in destination_model_entries),
    )
    origin_seed_entries: tuple[SeedPlanEntry, ...] = build_origin_seed_entries(
        project=origin_project,
        selected_names=frozenset(entry.name for entry in destination_seed_entries),
    )
    return (
        clone_plan,
        destination_model_entries,
        destination_seed_entries,
        origin_model_entries,
        origin_seed_entries,
    )
