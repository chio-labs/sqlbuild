"""Shared model materialization display labels."""

from __future__ import annotations

from sqlbuild.compiler.planner.models import ModelPlanEntry
from sqlbuild.compiler.planner.types import (
    HistoricalInput,
    IncrementalMode,
    MaterializationType,
    PlanAction,
)
from sqlbuild.shared.types import ExecutionResourceKind

_INCREMENTAL_ACTIONS: frozenset[PlanAction] = frozenset(
    {
        PlanAction.INCREMENTAL_APPEND,
        PlanAction.INCREMENTAL_DELETE_INSERT,
        PlanAction.INCREMENTAL_MERGE,
    }
)


def model_materialization_label(entry: ModelPlanEntry) -> str:
    """Return the full materialization label used in plan summaries."""

    if entry.materialization_type == MaterializationType.VIEW:
        return MaterializationType.VIEW.value
    if entry.materialization_type == MaterializationType.TABLE:
        return MaterializationType.TABLE.value
    if entry.materialization_type == MaterializationType.INCREMENTAL:
        return _incremental_label(entry)
    if entry.materialization_type == MaterializationType.SNAPSHOT:
        return _snapshot_label(entry, include_prefix=True)
    if entry.materialization_type == MaterializationType.CUSTOM:
        custom_name: str = entry.custom_materialization_name or MaterializationType.CUSTOM.value
        return f"{custom_name} (custom)"
    return entry.materialization_type.value


def model_resource_type(entry: ModelPlanEntry | None) -> str:
    """Return the left-column resource type used in execution progress rows."""

    if entry is None:
        return MaterializationType.TABLE.value
    if entry.materialization_type == MaterializationType.VIEW:
        return MaterializationType.VIEW.value
    if entry.materialization_type == MaterializationType.CUSTOM:
        return MaterializationType.CUSTOM.value
    if entry.materialization_type == MaterializationType.SNAPSHOT:
        return MaterializationType.SNAPSHOT.value
    return MaterializationType.TABLE.value


def materialization_type_display(resource_kind: ExecutionResourceKind) -> str:
    """Return the left-column resource type for active progress rows."""

    return resource_kind.value


def model_execution_annotation(entry: ModelPlanEntry | None) -> str:
    """Return the parenthesized model annotation used in execution progress rows."""

    if entry is None:
        return ""
    if entry.materialization_type == MaterializationType.SNAPSHOT:
        return _snapshot_label(entry, include_prefix=False)
    is_incremental: bool = (
        entry.action in _INCREMENTAL_ACTIONS
        or entry.materialization_type == MaterializationType.INCREMENTAL
    )
    if not is_incremental:
        return ""
    parts: list[str] = []
    if entry.incremental_strategy:
        parts.append(entry.incremental_strategy)
    return ", ".join(parts)


def _incremental_label(entry: ModelPlanEntry) -> str:
    strategy: str = entry.incremental_strategy or MaterializationType.INCREMENTAL.value
    parts: list[str] = []
    if entry.cursor_type is not None:
        parts.append(entry.cursor_type)
    if entry.incremental_mode == IncrementalMode.MICROBATCH:
        parts.append("microbatch")
    if parts:
        return f"{strategy} ({', '.join(parts)})"
    return strategy


def _snapshot_label(entry: ModelPlanEntry, *, include_prefix: bool) -> str:
    parts: list[str] = []
    if entry.snapshot_strategy:
        parts.append(entry.snapshot_strategy)
    if entry.observed_at_column is not None:
        historical_input: str = entry.historical_input or HistoricalInput.SNAPSHOT.value
        parts.append(f"historical {historical_input}")
    if not parts:
        return MaterializationType.SNAPSHOT.value if include_prefix else ""
    label: str = ", ".join(parts)
    if include_prefix:
        return f"snapshot ({label})"
    return label
