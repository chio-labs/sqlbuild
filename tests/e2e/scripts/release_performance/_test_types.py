"""Test types for the release performance comparison."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReleasePerformanceTestCase:
    description: str
    inspection_models: int
    build_models: int
    expected_return_code: int
    expected_fragments: tuple[str, ...]
