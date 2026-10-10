"""Test case types for native project graph integration tests."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NativeGraphSelectionTestCase:
    """A real compile selection resolved on the project's native graph."""

    description: str
    select: tuple[str, ...]
    expected_models: frozenset[str]
    expected_graph_builds: int


@dataclass(frozen=True)
class NativeGraphSelectorErrorTestCase:
    """A compile selector the native grammar rejects with the planner's error."""

    description: str
    select: str
    expected_error: str
