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
from sqlbuild.compiler.planner.models import (
    CursorOverrides,
    ModelPlanEntry,
    PlanOutput,
    SeedPlanEntry,
)
from sqlbuild.compiler.python_nodes.types import (
    PythonIdentityStatus,
    PythonNodeKind,
    PythonRunPhase,
)
from sqlbuild.compiler.references.types import ExternalSqlReferenceResolver
from sqlbuild.executor.custom.models import PrepareVersionContext


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
    changes_only: bool = False
    auto_load_sources: bool = False
    reload_sources: bool = False
    connection_config: dict[str, object] | None = None
    cli_vars: dict[str, object] | None = None
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None = None
    resolve_python_run_selectors: bool = False


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
