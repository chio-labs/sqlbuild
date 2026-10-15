"""Compiler pipeline models."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from functools import cached_property
from typing import Any

import sqlbuild._native as _native
from sqlbuild._native import (
    LineageGraphViews,
    PythonPlanEntry,
    lineage_graph_views,
)
from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledProjectView
from sqlbuild.compiler.planner.models import (
    PlanOutput,
)


@dataclass(frozen=True)
class ProjectGraph:
    """Static compiled project graph held natively; dict views are built only when read."""

    project: CompiledProjectView
    native: _native.NativeProjectGraph = field(compare=False, repr=False)

    @cached_property
    def lineage_views(self) -> LineageGraphViews:
        """Lineage edges and selector indexes as dicts, converted from the native graph once."""

        return lineage_graph_views(self.native)

    @property
    def upstream_deps(self) -> dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]]:
        """Lineage upstream edges, SQL tests stripped."""

        return self.lineage_views.upstream_deps

    @property
    def downstream_deps(self) -> dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]]:
        """Lineage downstream edges sorted by `(resource type, name)`."""

        return self.lineage_views.downstream_deps

    @property
    def tag_index(self) -> dict[str, frozenset[CompiledObjectKey]]:
        """Tag to tagged models, seeds and functions."""

        return self.lineage_views.tag_index

    @property
    def path_index(self) -> dict[CompiledObjectKey, str]:
        """Model key to its folder below `models/`."""

        return self.lineage_views.path_index

    @property
    def all_keys(self) -> dict[str, CompiledObjectKey]:
        """Selector name to key."""

        return self.lineage_views.all_keys


@dataclass(frozen=True)
class CompilePipelineResult:
    """Complete output from the compile-and-plan pipeline."""

    project: CompiledProjectView
    plan_output: PlanOutput
    custom_materializations: dict[str, Callable[..., Any]] = field(default_factory=dict)
    python_node_names: frozenset[str] = field(default_factory=frozenset)
    python_plan_entries: tuple[PythonPlanEntry, ...] = field(default_factory=tuple)
    compile_seconds: float | None = None
    planning_seconds: float | None = None
