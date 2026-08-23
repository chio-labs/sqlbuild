"""Test case types for kata performance guards."""

from dataclasses import dataclass


@dataclass(frozen=True)
class KataPerformanceGuardTestCase:
    description: str
    model_count: int
    expected_max_seconds: float
