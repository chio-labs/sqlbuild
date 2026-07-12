"""Model materialization display label implementations."""

from __future__ import annotations

from sqlbuild.compiler.planner.models import ModelPlanEntry
from sqlbuild.compiler.planner.types import (
    HistoricalInput,
    IncrementalMode,
    MaterializationType,
    PlanAction,
    RelationReuseKind,
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
    reuse_label: str = relation_reuse_label(entry)
    if entry.materialization_type == MaterializationType.VIEW:
        return _append_reuse_label(
            base_label=MaterializationType.VIEW.value, reuse_label=reuse_label
        )
    if entry.materialization_type == MaterializationType.TABLE:
        return _append_reuse_label(
            base_label=MaterializationType.TABLE.value, reuse_label=reuse_label
        )
    if entry.materialization_type == MaterializationType.INCREMENTAL:
        return _append_reuse_label(base_label=_incremental_label(entry), reuse_label=reuse_label)
    if entry.materialization_type == MaterializationType.SNAPSHOT:
        return _append_reuse_label(
            base_label=_snapshot_label(entry=entry, include_prefix=True), reuse_label=reuse_label
        )
    if entry.materialization_type == MaterializationType.CUSTOM:
        custom_name: str = entry.custom_materialization_name or MaterializationType.CUSTOM.value
        return _append_reuse_label(base_label=f"{custom_name} (custom)", reuse_label=reuse_label)
    return _append_reuse_label(base_label=entry.materialization_type.value, reuse_label=reuse_label)


def model_resource_type(entry: ModelPlanEntry | None) -> str:
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
    return resource_kind.value


def model_execution_annotation(entry: ModelPlanEntry | None) -> str:
    if entry is None:
        return ""
    reuse_label: str = relation_reuse_label(entry)
    if entry.materialization_type == MaterializationType.SNAPSHOT:
        snapshot_label: str = _snapshot_label(entry=entry, include_prefix=False)
        return _join_annotation_parts(snapshot_label, reuse_label)
    is_incremental: bool = (
        entry.action in _INCREMENTAL_ACTIONS
        or entry.materialization_type == MaterializationType.INCREMENTAL
    )
    if not is_incremental:
        return reuse_label
    parts: list[str] = []
    if entry.incremental_strategy:
        parts.append(entry.incremental_strategy)
    if reuse_label:
        parts.append(reuse_label)
    return ", ".join(parts)


def relation_reuse_label(entry: ModelPlanEntry | None) -> str:
    if entry is None or entry.relation_reuse is None:
        return ""
    copy_mode: str = "hard-copy" if entry.relation_reuse.hard_copy else "cheap"
    reuse_kind: str = (
        "seeded reuse"
        if entry.relation_reuse.kind == RelationReuseKind.SEEDED_RELATION_REUSE
        else "reuse"
    )
    return (
        f"{copy_mode} {reuse_kind} from reuse origin target "
        f"{entry.relation_reuse.reuse_from_target_name}"
    )


def _append_reuse_label(*, base_label: str, reuse_label: str) -> str:
    if not reuse_label:
        return base_label
    return f"{base_label} ({reuse_label})"


def _join_annotation_parts(*parts: str) -> str:
    return ", ".join(part for part in parts if part)


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


def _snapshot_label(*, entry: ModelPlanEntry, include_prefix: bool) -> str:
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
