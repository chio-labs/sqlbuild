from dataclasses import dataclass


@dataclass(frozen=True)
class BackgroundSqlTestPlanningTestCase:
    description: str
    enabled: bool
    expected_planner_calls: int
    expected_error: str | None = None
