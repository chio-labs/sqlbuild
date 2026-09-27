"""Test types for same-runner compile performance comparisons."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CompilePerformanceRatioTestCase:
    description: str
    kind: str
    models: int
    max_ratio: str
    expected_return_code: int
    expected_fragments: tuple[str, ...]
