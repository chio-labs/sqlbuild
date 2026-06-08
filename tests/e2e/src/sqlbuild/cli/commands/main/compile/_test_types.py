"""Test case types for compile command performance guards."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CompilePerformanceGuardTestCase:
    description: str
    model_count: int
    expected_max_seconds: float
