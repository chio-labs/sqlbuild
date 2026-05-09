from dataclasses import dataclass
from pathlib import Path

from sqlbuild.compiler.planner.models import ScenarioExecutionPlan
from sqlbuild.compiler.planner.types import ScenarioArtifactKind
from sqlbuild.executor.scenario.models import ScenarioSnapshotInputSpec


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
class ScenarioSnapshotRelationPathErrorTestCase:
    description: str
    kind: ScenarioArtifactKind
    logical_name: str
    expected_error_type: type[Exception]
