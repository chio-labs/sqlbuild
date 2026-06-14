"""dbt interop domain models."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.integrations.dbt.types import (
    DbtCombinedGraphOwner,
    DbtCombinedGraphResourceType,
    DbtInteropCommand,
    DbtInteropSkipReason,
)


@dataclass(frozen=True)
class DbtCliOptions:
    """Resolved dbt CLI options shared by dbt commands."""

    project_dir: Path | None = None
    profiles_dir: Path | None = None
    target: str | None = None
    target_path: Path | None = None
    vars: str | None = None
    state: Path | None = None
    defer: bool = False


@dataclass(frozen=True)
class DbtCliConfigOverrides:
    """dbt config values supplied by CLI flags."""

    project_dir: str | None = None
    profiles_dir: str | None = None
    target: str | None = None
    target_path: str | None = None

    @property
    def has_any(self) -> bool:
        """Return whether any dbt CLI config flag was supplied."""

        return any(
            value is not None
            for value in (self.project_dir, self.profiles_dir, self.target, self.target_path)
        )


@dataclass(frozen=True)
class ResolvedDbtConfig:
    """Resolved dbt config after applying CLI overrides."""

    project_dir: Path | None
    profiles_dir: Path | None
    target: str | None
    target_path: Path | None


@dataclass(frozen=True)
class DbtProjectProfileMetadata:
    """dbt project metadata needed for profile resolution."""

    project_name: str
    profile_name: str
    target_path: str


@dataclass(frozen=True)
class RawDbtProfile:
    """Raw dbt profile payload loaded from profiles.yml."""

    name: str
    default_target: str | None
    outputs: dict[str, dict[str, object]]


@dataclass(frozen=True)
class SelectedDbtProfileOutput:
    """Selected dbt profile target output before rendering."""

    profile_name: str
    target_name: str
    output: dict[str, object]


@dataclass(frozen=True)
class ResolvedDbtProfileOutput:
    """Rendered dbt profile target output."""

    project_dir: Path
    profiles_dir: Path
    profile_name: str
    target_name: str
    output: dict[str, object]

    @property
    def adapter_type(self) -> str:
        """Return the dbt adapter type from the rendered output."""

        value: object | None = self.output.get("type")
        return value if isinstance(value, str) else ""


@dataclass(frozen=True)
class NormalizedDbtProfileConnection:
    """Rendered dbt profile output normalized for SQLBuild."""

    adapter: str
    connection: dict[str, object]
    target_schema: str | None = None
    target_database: str | None = None
    warnings: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DbtProfileConnectionRequest:
    """Request to resolve one dbt-profile-backed SQLBuild connection."""

    sqlbuild_project_dir: Path
    dbt_project_dir: Path | None
    profiles_dir: Path | None
    profile_name: str | None
    target_name: str | None
    cli_vars: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class DbtInitProgressCallbacks:
    """Optional progress hooks for `sqb dbt init` phases."""

    start: Callable[[str], None] | None = None
    complete: Callable[[str], None] | None = None


@dataclass(frozen=True)
class DbtInitRequest:
    """Request to initialize a SQLBuild project from a dbt project."""

    cwd: Path
    dbt_project_dir: Path
    profiles_dir: Path | None
    profile_name: str | None
    target_name: str | None
    sqb_output_dir: Path | None
    dry_run: bool = False
    overwrite: bool = False
    skip_dbt_debug: bool = False
    progress_callbacks: DbtInitProgressCallbacks = field(default_factory=DbtInitProgressCallbacks)


@dataclass(frozen=True)
class DbtInitResult:
    """Result from `sqb dbt init`."""

    output_dir: Path
    project_file: Path
    project_name: str
    adapter: str
    target_name: str
    profile_name: str
    toml: str
    warnings: tuple[str, ...] = field(default_factory=tuple)
    dry_run: bool = False


@dataclass(frozen=True)
class DbtCommandResult:
    """Completed dbt command output."""

    argv: tuple[str, ...]
    returncode: int
    stdout: str = ""
    stderr: str = ""


@dataclass(frozen=True)
class DbtNodeMessage:
    """One dbt log message attached to a dbt node."""

    level: str
    message: str


@dataclass(frozen=True)
class DbtNodeExecutionResult:
    """One dbt node execution result parsed from JSON logs."""

    unique_id: str
    resource_type: str
    node_name: str
    status: str
    index: int | None
    total: int | None
    execution_time: float | None
    materialized: str | None = None
    relation_name: str | None = None
    database: str | None = None
    schema: str | None = None
    node_checksum: str | None = None
    messages: tuple[DbtNodeMessage, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DbtLsNode:
    """One node returned by `dbt ls --output json`."""

    unique_id: str
    resource_type: str | None = None
    package_name: str | None = None
    name: str | None = None
    original_file_path: str | None = None
    payload: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class DbtLsResult:
    """Parsed result from one dbt ls invocation."""

    nodes: tuple[DbtLsNode, ...]
    command: DbtCommandResult


@dataclass(frozen=True, order=True)
class DbtCombinedGraphKey:
    """Stable owner-qualified key for one combined dbt/SQLBuild graph node."""

    owner: DbtCombinedGraphOwner
    resource_type: DbtCombinedGraphResourceType
    name: str

    def __post_init__(self) -> None:
        from sqlbuild.integrations.dbt.types import (
            DbtCombinedGraphOwner,
            DbtCombinedGraphResourceType,
        )

        object.__setattr__(self, "owner", DbtCombinedGraphOwner(self.owner))
        object.__setattr__(
            self,
            "resource_type",
            DbtCombinedGraphResourceType(self.resource_type),
        )

    @property
    def stable_id(self) -> str:
        """Return a stable string form for plan JSON and diagnostics."""

        return f"{self.owner}:{self.resource_type}:{self.name}"


@dataclass(frozen=True)
class DbtCombinedGraph:
    """Combined downstream-only dbt and SQLBuild graph."""

    nodes: frozenset[DbtCombinedGraphKey]
    upstream_deps: dict[DbtCombinedGraphKey, tuple[DbtCombinedGraphKey, ...]]
    downstream_deps: dict[DbtCombinedGraphKey, tuple[DbtCombinedGraphKey, ...]]


@dataclass(frozen=True)
class DbtInteropRoutedArgs:
    """Arguments split for a future `sqb dbt` command execution."""

    command: DbtInteropCommand
    select: tuple[str, ...] = field(default_factory=tuple)
    exclude: tuple[str, ...] = field(default_factory=tuple)
    dbt_args: tuple[str, ...] = field(default_factory=tuple)
    sqlbuild_args: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DbtInteropSelectionResult:
    """SQLBuild-side selection produced from `sqb dbt` selectors."""

    sqlbuild_model_names: tuple[str, ...] = field(default_factory=tuple)
    dbt_required_unique_ids: tuple[str, ...] = field(default_factory=tuple)
    dbt_anchor_terms: tuple[str, ...] = field(default_factory=tuple)
    dbt_anchor_unique_ids_by_term: dict[str, tuple[str, ...]] = field(default_factory=dict)
    path_translations: tuple[tuple[str, str], ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DbtInteropPlan:
    """Plan output for one future `sqb dbt` command."""

    command: DbtInteropCommand
    dbt_command_argv: tuple[str, ...]
    dbt_selected_nodes: tuple[DbtLsNode, ...]
    dbt_selected_unique_ids: tuple[str, ...]
    sqlbuild_command_argvs: tuple[tuple[str, ...], ...]
    selection: DbtInteropSelectionResult
    sqlbuild_plan_output: PlanOutput | None = None
    dbt_required_selector_terms: tuple[str, ...] = field(default_factory=tuple)
    supplemental_dbt_command_argvs: tuple[tuple[str, ...], ...] = field(default_factory=tuple)
    dbt_skip_reason: DbtInteropSkipReason | None = None
    sqlbuild_skip_reason: DbtInteropSkipReason | None = None
    warnings: tuple[str, ...] = field(default_factory=tuple)
