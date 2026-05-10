from dataclasses import dataclass
from pathlib import Path

from sqlbuild.compiler.planner.models import ScenarioExecutionPlan
from sqlbuild.compiler.planner.types import ScenarioArtifactKind
from sqlbuild.executor.scenario.models import (
    ScenarioSnapshotCapturePlan,
    ScenarioSnapshotFileStats,
    ScenarioSnapshotInputSpec,
    ScenarioSnapshotManifest,
)
from sqlbuild.executor.scenario.types import ScenarioSnapshotState
from sqlbuild.executor.shared.types import ExecutionStatus


@dataclass(frozen=True)
class ScenarioSnapshotPathTestCase:
    description: str
    project_dir: Path
    scenario_name: str
    kind: ScenarioArtifactKind
    logical_name: str
    expected_root: Path
    expected_manifest_path: Path
    expected_relation_path: Path


@dataclass(frozen=True)
class ScenarioSnapshotFingerprintTestCase:
    description: str
    scenario_name: str
    input_specs: tuple[ScenarioSnapshotInputSpec, ...]
    equivalent_input_specs: tuple[ScenarioSnapshotInputSpec, ...]
    changed_input_specs: tuple[ScenarioSnapshotInputSpec, ...]
    expected_matches_equivalent: bool
    expected_differs_from_changed: bool


@dataclass(frozen=True)
class ScenarioSnapshotInputSpecsFromPlanTestCase:
    description: str
    scenario_plan: ScenarioExecutionPlan
    expected_input_specs: tuple[ScenarioSnapshotInputSpec, ...]
    changed_check_plan: ScenarioExecutionPlan
    changed_fixture_plan: ScenarioExecutionPlan
    expected_check_fingerprint_matches: bool
    expected_fixture_fingerprint_differs: bool


@dataclass(frozen=True)
class ScenarioSnapshotFreshnessTestCase:
    description: str
    manifest_fingerprint: str
    current_fingerprint: str
    expected_is_fresh: bool


@dataclass(frozen=True)
class ScenarioSnapshotManifestIoTestCase:
    description: str
    manifest: ScenarioSnapshotManifest
    expected_json_fragments: tuple[str, ...]


@dataclass(frozen=True)
class ScenarioSnapshotStateTestCase:
    description: str
    manifest: ScenarioSnapshotManifest | None
    manifest_contents: str | None
    expected_state: ScenarioSnapshotState
    expected_has_manifest: bool
    expected_error_code: str | None = None
    expected_error_fragment: str | None = None


@dataclass(frozen=True)
class ScenarioSnapshotJsonlRoundTripTestCase:
    description: str
    relative_file_path: Path
    rows: tuple[dict[str, object], ...]
    expected_stats: ScenarioSnapshotFileStats
    expected_file_contents: str
    expected_rows: tuple[dict[str, object], ...]


@dataclass(frozen=True)
class ScenarioSnapshotJsonlErrorTestCase:
    description: str
    file_contents: str
    expected_error_fragment: str


@dataclass(frozen=True)
class ScenarioLocalSnapshotLoadTestCase:
    description: str
    columns: tuple[tuple[str, str, str], ...]
    rows: tuple[dict[str, object], ...]
    expected_table_name: str
    expected_summary_row: tuple[object, ...]


@dataclass(frozen=True)
class ScenarioLocalSnapshotLoadErrorTestCase:
    description: str
    columns: tuple[tuple[str, str, str], ...]
    file_contents: str
    expected_error_code: str
    expected_error_fragments: tuple[str, ...]


@dataclass(frozen=True)
class ScenarioSnapshotCapturePlanTestCase:
    description: str
    project_dir: Path
    scenario_plan: ScenarioExecutionPlan
    expected_capture_plan: ScenarioSnapshotCapturePlan
    expected_manifest: ScenarioSnapshotManifest


@dataclass(frozen=True)
class ScenarioSnapshotRelationPathErrorTestCase:
    description: str
    kind: ScenarioArtifactKind
    logical_name: str
    expected_error_type: type[Exception]


@dataclass(frozen=True)
class ScenarioSnapshotLocalTypeMappingTestCase:
    description: str
    sqlglot_dialect: str | None
    warehouse_type: str
    expected_local_type: str
    local_type_overrides: dict[str, str] | None = None


@dataclass(frozen=True)
class ExecuteScenarioSnapshotCaptureStepsTestCase:
    description: str
    retain: bool
    fail_on_create_target: str | None
    fail_on_seed: bool
    fail_on_query_target: str | None
    expected_status: ExecutionStatus
    expected_retained: bool
    expected_fixture_result_count: int
    expected_seed_result_count: int
    expected_has_capture_result: bool
    expected_has_cleanup_result: bool
    expected_error_fragment: str | None = None
