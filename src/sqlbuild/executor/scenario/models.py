"""Scenario executor domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from sqlbuild.adapter.shared.models import LifeCycleEvent
from sqlbuild.compiler.planner.models import CompiledRelationTarget, ScenarioRelationMap
from sqlbuild.compiler.planner.types import MaterializationType, ScenarioArtifactKind
from sqlbuild.executor.build.models import SeedExecutionResult
from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.executor.scenario.types import ScenarioSnapshotState
from sqlbuild.executor.shared.types import ExecutionStatus


@dataclass(frozen=True)
class ScenarioFixtureExecutionResult:
    """Outcome of materializing one scenario fixture relation."""

    scenario_name: str
    kind: ScenarioArtifactKind
    logical_name: str
    target_relation: str
    status: ExecutionStatus
    lifecycle_events: tuple[LifeCycleEvent, ...] = field(default_factory=tuple)
    error_message: str | None = None


@dataclass(frozen=True)
class ScenarioCleanupTarget:
    """One planned scenario-owned relation selected for cleanup."""

    kind: ScenarioArtifactKind
    logical_name: str
    target_relation: str
    materialization_type: MaterializationType = MaterializationType.TABLE


@dataclass(frozen=True)
class ScenarioSnapshotColumn:
    """One column captured in a local scenario snapshot relation."""

    name: str
    warehouse_type: str
    local_type: str


@dataclass(frozen=True)
class ScenarioSnapshotRelation:
    """One captured relation recorded in a local scenario snapshot manifest."""

    kind: ScenarioArtifactKind
    logical_name: str
    file_path: Path
    row_count: int
    byte_count: int
    columns: tuple[ScenarioSnapshotColumn, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ScenarioSnapshotManifest:
    """Metadata for one local scenario snapshot."""

    version: int
    scenario_name: str
    captured_at: str
    capture_adapter: str
    capture_dialect: str
    sqlbuild_version: str
    input_fingerprint: str
    total_rows: int
    total_bytes: int
    relations: tuple[ScenarioSnapshotRelation, ...] = field(default_factory=tuple)
    format: str = "jsonl"


@dataclass(frozen=True)
class ScenarioSnapshotInputSpec:
    """Stable input requirement used to fingerprint local scenario snapshots."""

    kind: ScenarioArtifactKind
    logical_name: str
    file_path: Path
    capture_sql: str


@dataclass(frozen=True)
class ScenarioSnapshotFileStats:
    """Write statistics for one durable local scenario snapshot file."""

    row_count: int
    byte_count: int


@dataclass(frozen=True)
class ScenarioSnapshotStateResult:
    """Manifest freshness classification for one local scenario snapshot."""

    state: ScenarioSnapshotState
    manifest_path: Path
    manifest: ScenarioSnapshotManifest | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class ScenarioSnapshotCaptureRelationPlan:
    """One scenario input relation planned for durable local snapshot capture."""

    kind: ScenarioArtifactKind
    logical_name: str
    source_target: CompiledRelationTarget
    file_path: Path
    capture_sql: str


@dataclass(frozen=True)
class ScenarioSnapshotCapturePlan:
    """Executor-side plan for capturing scenario inputs into local snapshot files."""

    scenario_name: str
    snapshot_root: Path
    manifest_path: Path
    input_fingerprint: str
    relations: tuple[ScenarioSnapshotCaptureRelationPlan, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ScenarioSnapshotCaptureRelationResult:
    """Outcome of capturing one scenario input relation into JSONL."""

    kind: ScenarioArtifactKind
    logical_name: str
    source_relation: str
    file_path: Path
    status: ExecutionStatus
    row_count: int = 0
    byte_count: int = 0
    error_message: str | None = None


@dataclass(frozen=True)
class ScenarioSnapshotCaptureResult:
    """Outcome of writing local snapshot files for one scenario capture plan."""

    scenario_name: str
    status: ExecutionStatus
    manifest_path: Path
    manifest: ScenarioSnapshotManifest | None = None
    relation_results: tuple[ScenarioSnapshotCaptureRelationResult, ...] = field(
        default_factory=tuple
    )
    error_message: str | None = None


@dataclass(frozen=True)
class ScenarioSnapshotCaptureRunResult:
    """Outcome of materializing inputs and writing one local scenario snapshot."""

    scenario_name: str
    status: ExecutionStatus
    retained: bool = False
    fixture_results: tuple[ScenarioFixtureExecutionResult, ...] = field(default_factory=tuple)
    seed_results: tuple[SeedExecutionResult, ...] = field(default_factory=tuple)
    capture_result: ScenarioSnapshotCaptureResult | None = None
    prepare_cleanup_result: ScenarioCleanupExecutionResult | None = None
    cleanup_result: ScenarioCleanupExecutionResult | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class ScenarioCleanupExecutionResult:
    """Outcome of dropping planned scenario-owned relations."""

    scenario_name: str
    status: ExecutionStatus
    targets: tuple[ScenarioCleanupTarget, ...] = field(default_factory=tuple)
    lifecycle_events: tuple[LifeCycleEvent, ...] = field(default_factory=tuple)
    error_message: str | None = None


@dataclass(frozen=True)
class ScenarioExpectedCheckExecutionResult:
    """Outcome of comparing one scenario model relation to expected SQL."""

    scenario_name: str
    model_name: str
    status: ExecutionStatus
    actual_row_count: int = 0
    expected_row_count: int = 0
    mismatched_row_count: int = 0
    error_message: str | None = None


@dataclass(frozen=True)
class ScenarioAssertionCheckExecutionResult:
    """Outcome of executing one zero-row scenario assertion."""

    scenario_name: str
    name: str
    status: ExecutionStatus
    failing_row_count: int = 0
    sample_rows: tuple[tuple[object, ...], ...] = field(default_factory=tuple)
    error_message: str | None = None


@dataclass(frozen=True)
class ScenarioRunResult:
    """Result for one scenario execution run."""

    scenario_name: str
    status: ExecutionStatus
    retained: bool = False
    relation_map: ScenarioRelationMap | None = None
    fixture_results: tuple[ScenarioFixtureExecutionResult, ...] = field(default_factory=tuple)
    seed_results: tuple[SeedExecutionResult, ...] = field(default_factory=tuple)
    model_results: tuple[ModelExecutionResult, ...] = field(default_factory=tuple)
    expected_results: tuple[ScenarioExpectedCheckExecutionResult, ...] = field(
        default_factory=tuple
    )
    assertion_results: tuple[ScenarioAssertionCheckExecutionResult, ...] = field(
        default_factory=tuple
    )
    prepare_cleanup_result: ScenarioCleanupExecutionResult | None = None
    cleanup_result: ScenarioCleanupExecutionResult | None = None
    error_message: str | None = None
