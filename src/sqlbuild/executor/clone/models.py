"""Clone execution models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.models import LifeCycleEvent
from sqlbuild.compiler.compile.models import CompiledObjectKey, CompiledRelationLocation
from sqlbuild.compiler.planner.models import (
    CloneSourcePlanEntry,
    FunctionPlanEntry,
    ModelPlanEntry,
    SeedPlanEntry,
)
from sqlbuild.executor.clone.types import CloneAction, CloneItemCallback, CloneStatus


@dataclass(frozen=True)
class CloneSourceEntries:
    """Origin and destination managed source entries for one clone run."""

    origin: tuple[CloneSourcePlanEntry, ...] = field(default_factory=tuple)
    destination: tuple[CloneSourcePlanEntry, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CloneExecutionInput:
    """All runtime inputs required to execute one clone plan."""

    source_entries: CloneSourceEntries
    origin_model_entries: tuple[ModelPlanEntry, ...]
    destination_model_entries: tuple[ModelPlanEntry, ...]
    origin_seed_entries: tuple[SeedPlanEntry, ...]
    destination_seed_entries: tuple[SeedPlanEntry, ...]
    destination_function_entries: tuple[FunctionPlanEntry, ...]
    execution_order: tuple[CompiledObjectKey, ...]
    adapter: BaseAdapter
    destination_connection: Any
    hard_copy: bool
    run_id: str
    query_change_tracking: bool
    upstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = field(
        default_factory=dict
    )
    dependency_locations: dict[CompiledObjectKey, CompiledRelationLocation] = field(
        default_factory=dict
    )
    on_item: CloneItemCallback | None = None


@dataclass(frozen=True)
class CloneItemResult:
    name: str
    action: CloneAction
    status: CloneStatus
    message: str | None = None
    origin_relation: str | None = None
    destination_relation: str | None = None
    duration_seconds: float | None = None
    executed_statements: tuple[LifeCycleEvent, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class PrephaseProgressRow:
    """One clone prephase progress row."""

    label: str
    name: str
    status: str
    duration_seconds: float | None = None
    caused_by_names: tuple[str, ...] = ()
    detail: str = ""


@dataclass(frozen=True)
class CloneExecutionResult:
    item_results: tuple[CloneItemResult, ...] = field(default_factory=tuple)
