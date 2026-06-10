"""Compiler pipeline models."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlbuild.compiler.compile.models.core import (
    CompiledObjectKey,
    CompiledProject,
)
from sqlbuild.compiler.discovery.models import DiscoveredProviderUsage
from sqlbuild.compiler.planner.models import ModelPlanEntry, PlanOutput, SeedPlanEntry
from sqlbuild.compiler.python_nodes.types import PythonNodeKind, PythonRunPhase
from sqlbuild.executor.custom.models import PrepareVersionContext


@dataclass(frozen=True)
class PythonPlanEntry:
    """Display-ready Python node entry for plan output."""

    name: str
    kind: PythonNodeKind
    phase: PythonRunPhase
    provider_usages: tuple[DiscoveredProviderUsage, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CompilePipelineResult:
    """Complete output from the compile-and-plan pipeline."""

    project: CompiledProject
    plan_output: PlanOutput
    manifest: dict[str, object] = field(default_factory=dict)
    custom_materializations: dict[str, Callable[..., Any]] = field(default_factory=dict)
    custom_prepare_version_functions: dict[str, Callable[[PrepareVersionContext], None]] = field(
        default_factory=dict
    )
    python_node_names: frozenset[str] = field(default_factory=frozenset)
    python_plan_entries: tuple[PythonPlanEntry, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ClonePipelineResult:
    """Prepared clone inputs for origin and destination target environments."""

    origin_project: CompiledProject
    destination_project: CompiledProject
    clone_plan: PlanOutput
    destination_model_entries: tuple[ModelPlanEntry, ...] = field(default_factory=tuple)
    destination_seed_entries: tuple[SeedPlanEntry, ...] = field(default_factory=tuple)
    origin_model_entries: tuple[ModelPlanEntry, ...] = field(default_factory=tuple)
    origin_seed_entries: tuple[SeedPlanEntry, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ProjectGraph:
    """Static compiled project graph without warehouse state."""

    project: CompiledProject
    upstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]]
    downstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]]
    tag_index: dict[str, frozenset[CompiledObjectKey]]
    path_index: dict[CompiledObjectKey, str]
    all_keys: dict[str, CompiledObjectKey]
