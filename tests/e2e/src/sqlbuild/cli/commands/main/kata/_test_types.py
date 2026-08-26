"""Test case types for kata performance guards."""

from dataclasses import dataclass


@dataclass(frozen=True)
class KataPerformanceGuardTestCase:
    description: str
    model_count: int
    hard_ceiling_seconds: int
    expected_max_elapsed_seconds: float
    expected_returncode: int
