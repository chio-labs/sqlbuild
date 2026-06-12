"""Clone execution."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.planner.models import ModelPlanEntry, SeedPlanEntry
from sqlbuild.compiler.planner.types import MaterializationType
from sqlbuild.executor.clone.helpers.operations import clone_relation, recreate_view
from sqlbuild.executor.clone.models import CloneExecutionResult, CloneItemResult


def execute_clone(
    *,
    origin_model_entries: tuple[ModelPlanEntry, ...],
    destination_model_entries: tuple[ModelPlanEntry, ...],
    origin_seed_entries: tuple[SeedPlanEntry, ...],
    destination_seed_entries: tuple[SeedPlanEntry, ...],
    adapter: BaseAdapter,
    origin_connection: Any,
    destination_connection: Any,
    hard_copy: bool,
) -> CloneExecutionResult:
    origin_models_by_name: dict[str, ModelPlanEntry] = {
        entry.name: entry for entry in origin_model_entries
    }
    origin_seeds_by_name: dict[str, SeedPlanEntry] = {
        entry.name: entry for entry in origin_seed_entries
    }
    results: list[CloneItemResult] = []

    destination_entry: SeedPlanEntry | ModelPlanEntry
    for destination_entry in (*destination_seed_entries, *destination_model_entries):
        origin_entry: SeedPlanEntry | ModelPlanEntry | None = origin_seeds_by_name.get(
            destination_entry.name
        )
        if origin_entry is None:
            origin_entry = origin_models_by_name.get(destination_entry.name)
        if origin_entry is None:
            continue
        if (
            isinstance(destination_entry, ModelPlanEntry)
            and destination_entry.materialization_type == MaterializationType.VIEW
        ):
            results.append(
                recreate_view(
                    destination_entry=destination_entry,
                    origin_entry=origin_entry,
                    adapter=adapter,
                    origin_connection=origin_connection,
                    destination_connection=destination_connection,
                )
            )
            continue
        results.append(
            clone_relation(
                destination_entry=destination_entry,
                origin_entry=origin_entry,
                adapter=adapter,
                origin_connection=origin_connection,
                destination_connection=destination_connection,
                hard_copy=hard_copy,
            )
        )

    return CloneExecutionResult(item_results=tuple(results))
