from dataclasses import dataclass, field
from pathlib import Path

from sqlbuild.executor.scenario.models import (
    ScenarioSnapshotCaptureLimits,
    ScenarioSnapshotCaptureResult,
)
from sqlbuild.executor.types import ExecutionStatus


@dataclass(frozen=True)
class ExecuteScenarioFixtureTestCase:
    description: str
    scenario_name: str
    expected_status: ExecutionStatus
    expected_target_relation: str
    expected_sql_fragment: str
    expected_error_fragment: str | None = None


@dataclass(frozen=True)
class ExecuteScenarioFixturesTestCase:
    description: str
    expected_result_count: int
    expected_statuses: tuple[ExecutionStatus, ...]
    expected_executed_target_count: int


@dataclass(frozen=True)
class ExecuteScenarioCleanupTestCase:
    description: str
    expected_status: ExecutionStatus
    expected_drop_targets: tuple[str, ...]
    unexpected_drop_targets: tuple[str, ...] = ()
    expected_error_fragment: str | None = None


@dataclass(frozen=True)
class ExecuteScenarioModelsTestCase:
    description: str
    expected_statuses: tuple[ExecutionStatus, ...]
    expected_model_names: tuple[str, ...]
    expected_sql_fragments: tuple[str, ...]
    expected_error_fragment: str | None = None


@dataclass(frozen=True)
class ExecuteScenarioSnapshotCaptureTestCase:
    description: str
    expected_result: ScenarioSnapshotCaptureResult
    expected_jsonl_files: dict[Path, str]
    expected_manifest_fragment: str
    expected_query_fragments: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ExecuteScenarioSnapshotCaptureLimitTestCase:
    description: str
    limits: ScenarioSnapshotCaptureLimits
    expected_error_fragment: str
    expected_missing_relative_path: Path
    expected_query_fragment: str
    unexpected_query_fragment: str
