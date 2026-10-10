"""Compiler pipeline models."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from functools import cached_property
from typing import Any

import sqlbuild._native as _native
from sqlbuild.compiler.compile.models import CompiledObjectKey, CompiledProject
from sqlbuild.compiler.discovery.models import DiscoveredProviderUsage
from sqlbuild.compiler.graph.main._lineage_graph_views import lineage_graph_views
from sqlbuild.compiler.graph.models import LineageGraphViews
from sqlbuild.compiler.planner.models import (
    CloneSourcePlanEntry,
    CursorOverrides,
    FunctionPlanEntry,
    ModelPlanEntry,
    PlannerRelationsContext,
    PlannerScope,
    PlanOutput,
    SeedPlanEntry,
    SqlTestSelection,
)
from sqlbuild.compiler.python_nodes.types import (
    PythonIdentityStatus,
    PythonNodeKind,
    PythonRunPhase,
)
from sqlbuild.compiler.references.types import ExternalSqlReferenceResolver


@dataclass(frozen=True)
class ProjectGraph:
    """Static compiled project graph held natively; dict views are built only when read."""

    project: CompiledProject
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
class CompilePipelineOptions:
    """Selection, deferral, and planning options for one compile pipeline run."""

    selected_target: str | None = None
    no_sql_validation: bool = False
    defer_to: str | None = None
    defer_sources_to: str | None = None
    source_deferral_enabled: bool = True
    select: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    cursor_overrides: CursorOverrides | None = None
    full_refresh: bool = False
    auto_load_sources: bool = False
    reload_sources: bool = False
    connection_config: dict[str, object] | None = None
    cli_vars: dict[str, object] | None = None
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None = None
    resolve_python_run_selectors: bool = False
    no_cache: bool = False
    max_microbatches: int | None = None
    selection_diagnostics: bool = False
    plan_sql_tests: bool = True
    record_migration_fingerprints: bool = True
    accepts_unit_test_selectors: bool = False
    sql_test_selection: SqlTestSelection = field(default_factory=SqlTestSelection)


@dataclass(frozen=True)
class PythonPlanEntry:
    """Display-ready Python node entry for plan output."""

    name: str
    kind: PythonNodeKind
    phase: PythonRunPhase
    identity_status: PythonIdentityStatus = PythonIdentityStatus.UNKNOWN
    current_definition_json: str | None = None
    previous_definition_json: str | None = None
    current_metadata_json: str | None = None
    previous_metadata_json: str | None = None
    provider_usages: tuple[DiscoveredProviderUsage, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class PythonRunPlanOutputs:
    """Plan output and Python entries after python-aware run selection."""

    plan_output: PlanOutput
    python_plan_entries: tuple[PythonPlanEntry, ...]
    selected_python_node_names: frozenset[str]


@dataclass(frozen=True)
class CompilePipelineResult:
    """Complete output from the compile-and-plan pipeline."""

    project: CompiledProject
    plan_output: PlanOutput
    custom_materializations: dict[str, Callable[..., Any]] = field(default_factory=dict)
    python_node_names: frozenset[str] = field(default_factory=frozenset)
    python_plan_entries: tuple[PythonPlanEntry, ...] = field(default_factory=tuple)
    compile_seconds: float | None = None
    planning_seconds: float | None = None


@dataclass(frozen=True)
class CompiledProjectPhaseResult:
    """Canonical project compilation output before command-specific planning."""

    project: CompiledProject
    connection_config: dict[str, object]
    compile_seconds: float


@dataclass(frozen=True)
class StaticCommandContext:
    """Shared compile, selection, and relation phases for focused commands."""

    project: CompiledProject
    scope: PlannerScope
    relations: PlannerRelationsContext
    connection_config: dict[str, object]
    compile_seconds: float


@dataclass(frozen=True)
class ClonePipelineOptions:
    """Compilation and selection options for one clone pipeline."""

    no_sql_validation: bool = False
    select: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    cli_vars: dict[str, object] | None = None
    no_cache: bool = False


@dataclass(frozen=True)
class ClonePipelineConnection:
    """Resolved destination connection used throughout clone compilation and planning."""

    config: dict[str, object]
    handle: Any


@dataclass(frozen=True)
class ClonePipelineResult:
    """Prepared clone inputs for origin and destination target environments."""

    origin_project: CompiledProject
    destination_project: CompiledProject
    clone_plan: PlanOutput
    destination_source_entries: tuple[CloneSourcePlanEntry, ...] = field(default_factory=tuple)
    destination_model_entries: tuple[ModelPlanEntry, ...] = field(default_factory=tuple)
    destination_seed_entries: tuple[SeedPlanEntry, ...] = field(default_factory=tuple)
    destination_function_entries: tuple[FunctionPlanEntry, ...] = field(default_factory=tuple)
    origin_model_entries: tuple[ModelPlanEntry, ...] = field(default_factory=tuple)
    origin_seed_entries: tuple[SeedPlanEntry, ...] = field(default_factory=tuple)
    origin_source_entries: tuple[CloneSourcePlanEntry, ...] = field(default_factory=tuple)
