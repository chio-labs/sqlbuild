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
    source_model_entries: tuple[ModelPlanEntry, ...],
    target_model_entries: tuple[ModelPlanEntry, ...],
    source_seed_entries: tuple[SeedPlanEntry, ...],
    target_seed_entries: tuple[SeedPlanEntry, ...],
    adapter: BaseAdapter,
    source_connection: Any,
    target_connection: Any,
    hard_copy: bool,
) -> CloneExecutionResult:
    source_models_by_name: dict[str, ModelPlanEntry] = {
        entry.name: entry for entry in source_model_entries
    }
    source_seeds_by_name: dict[str, SeedPlanEntry] = {
        entry.name: entry for entry in source_seed_entries
    }
    results: list[CloneItemResult] = []

    target_entry: SeedPlanEntry | ModelPlanEntry
    for target_entry in (*target_seed_entries, *target_model_entries):
        source_entry: SeedPlanEntry | ModelPlanEntry | None = source_seeds_by_name.get(
            target_entry.name
        )
        if source_entry is None:
            source_entry = source_models_by_name.get(target_entry.name)
        if source_entry is None:
            continue
        if (
            isinstance(target_entry, ModelPlanEntry)
            and target_entry.materialization_type == MaterializationType.VIEW
        ):
            results.append(
                recreate_view(
                    target_entry=target_entry,
                    source_entry=source_entry,
                    adapter=adapter,
                    source_connection=source_connection,
                    target_connection=target_connection,
                )
            )
            continue
        results.append(
            clone_relation(
                target_entry=target_entry,
                source_entry=source_entry,
                adapter=adapter,
                source_connection=source_connection,
                target_connection=target_connection,
                hard_copy=hard_copy,
            )
        )

    return CloneExecutionResult(item_results=tuple(results))
