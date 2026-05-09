from dataclasses import dataclass

from sqlbuild.executor.shared.types import ExecutionStatus


@dataclass(frozen=True)
class ScenarioFixtureMaterializationIntegrationTestCase:
    description: str
    expected_statuses: tuple[ExecutionStatus, ...]
    expected_rows_by_relation: dict[str, tuple[tuple[object, ...], ...]]


@dataclass(frozen=True)
class ScenarioCleanupIntegrationTestCase:
    description: str
    expected_status: ExecutionStatus
    planned_relation_names: tuple[str, ...]
    retained_relation_name: str


@dataclass(frozen=True)
class ScenarioFixtureFailureIntegrationTestCase:
    description: str
    expected_status: ExecutionStatus
    expected_error_fragment: str
    expected_log_fragment: str


@dataclass(frozen=True)
class ScenarioProjectSeedLoadIntegrationTestCase:
    description: str
    expected_statuses: tuple[ExecutionStatus, ...]
    expected_rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class ScenarioModelBuildIntegrationTestCase:
    description: str
    expected_statuses: tuple[ExecutionStatus, ...]
    expected_rows: tuple[tuple[object, ...], ...]
