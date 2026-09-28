from dataclasses import dataclass


@dataclass(frozen=True)
class BackgroundSqlTestPlanningTestCase:
    description: str
    enabled: bool
    expected_planner_calls: int
    expected_error: str | None = None


@dataclass(frozen=True)
class MigrationFingerprintCacheTestCase:
    description: str
    requests: tuple[tuple[str, dict[str, str], str], ...]
    expected_computations: int
