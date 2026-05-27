"""Seeded virtual execution-plan adaptation helpers."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.planner.models import CursorBounds, CursorOverrides, PlanOutput
from sqlbuild.compiler.planner.types import IncrementalStrategy, MaterializationType, PlanAction
from sqlbuild.virtual.state.models import PhysicalRelationRecord


def adapt_plan_for_seeded_virtual_execution(
    *,
    adapter: BaseAdapter,
    plan_output: PlanOutput,
    bound_physical_relations: dict[str, PhysicalRelationRecord],
    expected_version_hashes: dict[str, str],
    cursor_overrides: CursorOverrides | None,
) -> PlanOutput:
    """Restore seeded incremental execution semantics for changed physical targets."""

    entries: list[Any] = []
    changed: bool = False
    for entry in plan_output.model_entries:
        if not _requires_seeded_incremental_adaptation(
            entry=entry,
            bound_physical_relations=bound_physical_relations,
            expected_version_hashes=expected_version_hashes,
        ):
            entries.append(entry)
            continue

        action: PlanAction | None = _incremental_action_for_strategy(
            strategy=entry.incremental_strategy
        )
        cursor_bounds: CursorBounds | None = _seeded_cursor_bounds(
            entry=entry,
            cursor_overrides=cursor_overrides,
        )
        if action == PlanAction.INCREMENTAL_DELETE_INSERT and cursor_bounds is None:
            entries.append(entry)
            continue
        if action is None:
            entries.append(entry)
            continue

        entries.append(
            replace(
                entry,
                action=action,
                cursor_bounds=cursor_bounds,
                resolved_sql=_bounded_seeded_resolved_sql(
                    adapter=adapter,
                    entry=entry,
                    cursor_bounds=cursor_bounds,
                ),
            )
        )
        changed = True

    if not changed:
        return plan_output
    return replace(plan_output, model_entries=tuple(entries))


def _requires_seeded_incremental_adaptation(
    *,
    entry: Any,
    bound_physical_relations: dict[str, PhysicalRelationRecord],
    expected_version_hashes: dict[str, str],
) -> bool:
    return (
        entry.action == PlanAction.CREATE_TABLE
        and entry.materialization_type == MaterializationType.INCREMENTAL
        and entry.name in bound_physical_relations
        and expected_version_hashes.get(entry.name)
        != bound_physical_relations[entry.name].version_hash
    )


def _incremental_action_for_strategy(*, strategy: str | None) -> PlanAction | None:
    if strategy == IncrementalStrategy.APPEND:
        return PlanAction.INCREMENTAL_APPEND
    if strategy == IncrementalStrategy.DELETE_INSERT:
        return PlanAction.INCREMENTAL_DELETE_INSERT
    if strategy == IncrementalStrategy.MERGE:
        return PlanAction.INCREMENTAL_MERGE
    return None


def _seeded_cursor_bounds(
    *, entry: Any, cursor_overrides: CursorOverrides | None
) -> CursorBounds | None:
    if entry.cursor_bounds is not None:
        return entry.cursor_bounds
    if cursor_overrides is None:
        return None
    if cursor_overrides.start_ts is not None and cursor_overrides.end_ts is not None:
        return CursorBounds(start=cursor_overrides.start_ts, end=cursor_overrides.end_ts)
    if cursor_overrides.start_int is not None and cursor_overrides.end_int is not None:
        return CursorBounds(start=cursor_overrides.start_int, end=cursor_overrides.end_int)
    return None


def _bounded_seeded_resolved_sql(
    *, adapter: BaseAdapter, entry: Any, cursor_bounds: CursorBounds | None
) -> str:
    if cursor_bounds is None or entry.cursor_column is None:
        return entry.resolved_sql
    return adapter.render_query_with_cursor_bounds(
        sql=entry.resolved_sql,
        cursor_column=entry.cursor_column,
        cursor_start=cursor_bounds.start,
        cursor_end=cursor_bounds.end,
        cursor_type=entry.cursor_type,
    )
