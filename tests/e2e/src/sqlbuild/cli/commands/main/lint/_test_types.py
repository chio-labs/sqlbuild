"""Test case types for lint command performance guards."""

from dataclasses import dataclass


@dataclass(frozen=True)
class LintPerformanceGuardTestCase:
    description: str
    model_count: int
    hard_ceiling_seconds: int
    expected_max_elapsed_seconds: float
    model_sql: str
    expected_exit_code: int = 0


@dataclass(frozen=True)
class LintPerformanceBehaviorTestCase:
    description: str
    expected_maximum: float
