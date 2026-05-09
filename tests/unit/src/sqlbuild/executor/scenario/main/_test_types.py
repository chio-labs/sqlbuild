from dataclasses import dataclass

from sqlbuild.executor.shared.types import ExecutionStatus


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
