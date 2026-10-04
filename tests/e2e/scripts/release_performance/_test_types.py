"""Test types for the release performance comparison."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReleasePerformanceTestCase:
    description: str
    inspection_models: int
    build_models: int
    dense_models: int
    expected_outcomes: tuple[tuple[int, bool], ...]
    expected_fragments: tuple[str, ...]
    expected_marked_projects: tuple[str, ...]
