"""Test case types for Rules performance guards."""

from dataclasses import dataclass


@dataclass(frozen=True)
class RulesPerformanceGuardTestCase:
    description: str
    model_count: int
    hard_ceiling_seconds: int
    expected_max_elapsed_seconds: float
    expected_returncode: int


@dataclass(frozen=True)
class UnusedCteContextTestCase:
    """Project whose framework context keeps a CTE reachable."""

    description: str
    files: dict[str, str]
    expected_returncode: int
    expected_finding_count: int
