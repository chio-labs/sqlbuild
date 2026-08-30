"""Virtual executor result models."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from sqlbuild.adapter.contract.models import RelationLookup
from sqlbuild.compiler.compile.models import (
    CompiledModel,
    CompiledProject,
    CompiledRelationLocation,
    CompiledSeed,
)
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.compiler.references.types import ExternalSqlReferenceResolver
from sqlbuild.cost.models import StatementExecutionTelemetry
from sqlbuild.executor.build.models import BuildExecutionResult, SchedulerState
from sqlbuild.executor.python_nodes.models import PythonNodeExecutionResult
from sqlbuild.provider.main.runtime import ProviderContainer
from sqlbuild.runtime.contracts.types import (
    ConnectionElapsedCallback,
    NodeStartCallback,
)
from sqlbuild.spec.contracts.models import SnapshotsConfig
from sqlbuild.virtual.executor.constants import (
    VIRTUAL_CLONE_FOUND_ACTIONS,
    VIRTUAL_CLONE_HYDRATED_ACTION,
    VIRTUAL_CLONE_MISSING_ACTION,
    VIRTUAL_CLONE_REUSED_ACTION,
    VIRTUAL_CLONE_SKIPPED_LOCKED_ACTION,
)
from sqlbuild.virtual.executor.types import VirtualPlanReadyCallback
from sqlbuild.virtual.planner.models import VirtualPlanOptions, VirtualPlanSemantics
from sqlbuild.virtual.state.models import (
    FunctionVersionRecord,
    ModelVersionRecord,
    PhysicalRelationRecord,
    SeedVersionRecord,
    SourceFreshnessRecord,
    VirtualEnvironmentCheckpointFunctionRefRecord,
    VirtualEnvironmentCheckpointModelRefRecord,
    VirtualEnvironmentCheckpointRecord,
    VirtualEnvironmentCheckpointSeedRefRecord,
    VirtualEnvironmentFunctionRefRecord,
    VirtualEnvironmentModelRefRecord,
    VirtualEnvironmentNodeRefRecord,
    VirtualEnvironmentRecord,
    VirtualEnvironmentSeedRefRecord,
)
from sqlbuild.virtual.state.types import (
    PhysicalArtifactType,
    StateOperationType,
    VirtualEnvironmentStatus,
)


@dataclass(frozen=True)
class VirtualBuildExecutionHooks:
    """Callbacks to use once a virtual build plan is ready."""

    on_node_start: NodeStartCallback | None = None
    on_node_complete: Callable[[object], None] | None = None
    on_sub_progress: Callable[[str], None] | None = None
    on_scheduler_state: Callable[[SchedulerState], None] | None = None
    on_statement_complete: Callable[[StatementExecutionTelemetry], None] | None = None


@dataclass(frozen=True)
class VirtualBuildOptions:
    """Execution options composing the shared virtual planning contract."""

    planning: VirtualPlanOptions = field(default_factory=VirtualPlanOptions)
    seed_only: bool = False
    fail_fast: bool = False
    allow_snapshot_schema_change: bool = False
    concurrency: int | None = None
    run_tests: bool = True
    run_audits: bool = True
    snapshots: SnapshotsConfig | None = None
    start_cursor_ts: datetime | None = None
    end_cursor_ts: datetime | None = None
    start_cursor_int: int | None = None
    end_cursor_int: int | None = None
    providers: ProviderContainer | None = None


@dataclass(frozen=True)
class VirtualBuildHooks:
    """Plan-ready, progress, and connection callbacks for one virtual build run."""

    on_plan_ready: VirtualPlanReadyCallback | None = None
    on_progress: Callable[[str], None] | None = None
    on_connection_start: Callable[[int], None] | None = None
    on_connection_complete: ConnectionElapsedCallback | None = None
    on_connection_error: ConnectionElapsedCallback | None = None


@dataclass(frozen=True)
class VirtualEnvironmentNames:
    """Resolved target VDE, physical target, and unsuffixed naming context."""

    target_vde_name: str
    physical_target_name: str | None = None
    unsuffixed_virtual_environment_name: str | None = None


@dataclass(frozen=True)
class PromoteOptions:
    """Selection and policy options for one virtual promote run."""

    select: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    allow_partial_promotion: bool = False
    include_stale_upstreams: bool = False
    no_sql_validation: bool = False
    cli_vars: dict[str, object] | None = None
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None = None


@dataclass(frozen=True)
class RollbackOptions:
    """Selection and policy options for one virtual rollback run."""

    checkpoint_id: str | None = None
    select: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    allow_partial_rollback: bool = False
    include_stale_upstreams: bool = False
    no_sql_validation: bool = False
    cli_vars: dict[str, object] | None = None
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None = None


@dataclass(frozen=True)
class CloneOptions:
    """Selection and policy options for one virtual clone run."""

    virtual_environment_name: str | None = None
    skip_locked: bool = False
    no_sql_validation: bool = False
    select: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    cli_vars: dict[str, object] | None = None
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None = None


@dataclass(frozen=True)
class VirtualBuildPipelineResult:
    """Result returned by the virtual build pipeline."""

    project: CompiledProject
    direct_plan_output: PlanOutput
    display_plan_output: PlanOutput
    execution_plan: PlanOutput
    execution_result: BuildExecutionResult
    virtual_environment_name: str
    python_node_results: tuple[PythonNodeExecutionResult, ...] = field(default_factory=tuple)
    compile_seconds: float | None = None
    planning_seconds: float | None = None


@dataclass(frozen=True)
class VirtualCloneItemResult:
    """One virtual clone hydration result."""

    artifact_type: PhysicalArtifactType
    artifact_name: str
    version_hash: str
    action: str
    message: str | None = None


@dataclass(frozen=True)
class VirtualCloneResult:
    """Result returned by virtual physical-version hydration."""

    mode: str
    origin_environment: str
    destination_environment: str
    destination_virtual_environment: str | None = None
    origin_state_used: bool = False
    item_results: tuple[VirtualCloneItemResult, ...] = field(default_factory=tuple)

    @property
    def selected_count(self) -> int:
        return len(self.item_results)

    @property
    def found_count(self) -> int:
        return sum(1 for item in self.item_results if item.action in VIRTUAL_CLONE_FOUND_ACTIONS)

    @property
    def hydrated_count(self) -> int:
        return sum(1 for item in self.item_results if item.action == VIRTUAL_CLONE_HYDRATED_ACTION)

    @property
    def reused_count(self) -> int:
        return sum(1 for item in self.item_results if item.action == VIRTUAL_CLONE_REUSED_ACTION)

    @property
    def missing_count(self) -> int:
        return sum(1 for item in self.item_results if item.action == VIRTUAL_CLONE_MISSING_ACTION)

    @property
    def skipped_locked_count(self) -> int:
        return sum(
            1 for item in self.item_results if item.action == VIRTUAL_CLONE_SKIPPED_LOCKED_ACTION
        )


@dataclass(frozen=True)
class StateOperationHandle:
    """Identity of one in-flight executor state operation."""

    operation_id: str
    operation_type: StateOperationType


@dataclass(frozen=True)
class VirtualProjectContext:
    """Compiled project graph plus active target VDE naming context."""

    graph: ProjectGraph
    unsuffixed_virtual_environment_name: str | None


@dataclass(frozen=True)
class PromoteEnvironmentState:
    """Bound refs and environment records read for one promote run."""

    source_refs: tuple[VirtualEnvironmentModelRefRecord, ...]
    target_refs: tuple[VirtualEnvironmentModelRefRecord, ...]
    source_function_refs: tuple[VirtualEnvironmentFunctionRefRecord, ...]
    from_seed_refs: tuple[VirtualEnvironmentSeedRefRecord, ...]
    to_seed_refs: tuple[VirtualEnvironmentSeedRefRecord, ...]
    source_environment: VirtualEnvironmentRecord | None
    target_environment: VirtualEnvironmentRecord | None
    source_freshness_records: tuple[SourceFreshnessRecord, ...]
    target_freshness_records: tuple[SourceFreshnessRecord, ...]


@dataclass(frozen=True)
class PromoteSemantics:
    """Source and target virtual plan semantics for one promote run."""

    source: VirtualPlanSemantics
    target: VirtualPlanSemantics


@dataclass(frozen=True)
class PromoteSelection:
    """Validated promote selection scope with source ref lookups."""

    selected_model_names: tuple[str, ...]
    selected_seed_names: tuple[str, ...]
    source_ref_map: dict[str, str]
    from_seed_ref_map: dict[str, str]


@dataclass(frozen=True)
class PromoteResolution:
    """Final ref hashes, staleness, and target status for one promote run."""

    selected_model_names: tuple[str, ...]
    selected_seed_names: tuple[str, ...]
    final_version_hashes: dict[str, str]
    final_seed_hashes: dict[str, str]
    stale_after: tuple[str, ...]
    status: VirtualEnvironmentStatus

    @property
    def promoted_model_count(self) -> int:
        return len(self.selected_model_names)


@dataclass(frozen=True)
class PromoteRefUpdate:
    """Target environment record and replacement ref groups to persist."""

    virtual_environment_record: VirtualEnvironmentRecord
    refs: tuple[VirtualEnvironmentModelRefRecord, ...]
    seed_refs: tuple[VirtualEnvironmentSeedRefRecord, ...]
    function_refs: tuple[VirtualEnvironmentFunctionRefRecord, ...]
    function_versions: dict[str, FunctionVersionRecord]
    refs_by_node_type: dict[str, tuple[VirtualEnvironmentNodeRefRecord, ...]]


@dataclass(frozen=True)
class VirtualEnvironmentPhysicalRelations:
    """Tracked physical relations backing an environment's model and seed refs."""

    model_relations: dict[str, PhysicalRelationRecord]
    seed_relations: dict[str, PhysicalRelationRecord]


@dataclass(frozen=True)
class RollbackCheckpointState:
    """Current ref map and resolved rollback checkpoint refs."""

    current_ref_map: dict[str, str]
    target_checkpoint: VirtualEnvironmentCheckpointRecord
    checkpoint_model_refs: tuple[VirtualEnvironmentCheckpointModelRefRecord, ...]
    checkpoint_function_refs: tuple[VirtualEnvironmentCheckpointFunctionRefRecord, ...]
    checkpoint_seed_refs: tuple[VirtualEnvironmentCheckpointSeedRefRecord, ...]


@dataclass(frozen=True)
class RollbackResolution:
    """Final ref hashes, scope, and target status for one rollback run."""

    final_version_hashes: dict[str, str]
    final_seed_hashes: dict[str, str]
    is_partial_scope: bool
    status: VirtualEnvironmentStatus
    rolled_back_model_names: tuple[str, ...]


@dataclass(frozen=True)
class CloneProjectContext:
    """Destination graph and origin/destination node lookups for one clone run."""

    destination_graph: ProjectGraph
    model_names: tuple[str, ...]
    seed_names: tuple[str, ...]
    destination_models_by_name: dict[str, CompiledModel]
    origin_models_by_name: dict[str, CompiledModel]
    destination_seeds_by_name: dict[str, CompiledSeed]
    origin_seeds_by_name: dict[str, CompiledSeed]


@dataclass(frozen=True)
class CloneVersions:
    """Resolved model and seed versions to hydrate for one clone run."""

    mode: str
    version_hashes: dict[str, str]
    model_versions: dict[str, ModelVersionRecord]
    seed_versions: dict[str, SeedVersionRecord]
    origin_state_used: bool = False


@dataclass(frozen=True)
class CloneOriginLookup:
    """Origin lookup locations, alias, and existence lookup for one clone run."""

    model_locations: dict[str, CompiledRelationLocation]
    seed_locations: dict[str, CompiledRelationLocation]
    lookup: RelationLookup


@dataclass(frozen=True)
class RollbackRefUpdate:
    """Environment record and replacement ref groups for one rollback run."""

    virtual_environment_record: VirtualEnvironmentRecord
    refs: tuple[VirtualEnvironmentModelRefRecord, ...]
    seed_refs: tuple[VirtualEnvironmentSeedRefRecord, ...]
    function_refs: tuple[VirtualEnvironmentFunctionRefRecord, ...]
    function_versions: dict[str, FunctionVersionRecord]
    refs_by_node_type: dict[str, tuple[VirtualEnvironmentNodeRefRecord, ...]]
