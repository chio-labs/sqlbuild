"""Virtual executor result models."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from sqlbuild.compiler.compile.models.core import (
    CompiledModel,
    CompiledProject,
    CompiledRelationLocation,
    CompiledSeed,
)
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.executor.build.models import BuildExecutionResult
from sqlbuild.executor.python_nodes.models import PythonNodeExecutionResult
from sqlbuild.shared.models import RelationLookup
from sqlbuild.shared.types import ExecutionResourceKind
from sqlbuild.virtual.planner.models import VirtualPlanSemantics
from sqlbuild.virtual.state.models import (
    FunctionVersionRecord,
    ModelVersionRecord,
    PhysicalRelationRecord,
    SeedVersionRecord,
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

    on_node_start: Callable[[str, ExecutionResourceKind], None] | None = None
    on_node_complete: Callable[[object], None] | None = None
    on_sub_progress: Callable[[str], None] | None = None


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
    item_results: tuple[VirtualCloneItemResult, ...] = field(default_factory=tuple)

    @property
    def selected_count(self) -> int:
        return len(self.item_results)

    @property
    def found_count(self) -> int:
        return sum(1 for item in self.item_results if item.action in {"hydrated", "reused"})

    @property
    def hydrated_count(self) -> int:
        return sum(1 for item in self.item_results if item.action == "hydrated")

    @property
    def reused_count(self) -> int:
        return sum(1 for item in self.item_results if item.action == "reused")

    @property
    def missing_count(self) -> int:
        return sum(1 for item in self.item_results if item.action == "missing")

    @property
    def skipped_locked_count(self) -> int:
        return sum(1 for item in self.item_results if item.action == "skipped_locked")


@dataclass(frozen=True)
class StateOperationHandle:
    """Identity of one in-flight executor state operation."""

    operation_id: str
    operation_type: StateOperationType


@dataclass(frozen=True)
class VirtualViewRefreshHooks:
    """Progress and connection callbacks for VDE view refresh phases."""

    on_progress: Callable[[str], None] | None = None
    on_connection_start: Callable[[int], None] | None = None
    on_connection_complete: Callable[[int, float], None] | None = None
    on_connection_error: Callable[[int, float], None] | None = None


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


@dataclass(frozen=True)
class CloneOriginLookup:
    """Origin lookup locations, alias, and existence lookup for one clone run."""

    model_locations: dict[str, CompiledRelationLocation]
    seed_locations: dict[str, CompiledRelationLocation]
    origin_database_alias: str | None
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
