"""Test case models for cursor algebra."""

from dataclasses import dataclass

from sqlbuild.compiler.planner.types import CursorGrain


@dataclass(frozen=True, kw_only=True)
class CursorAlgebraMatrixCase:
    """One exhaustive grain, position, and temporal representation combination."""

    description: str
    grain: CursorGrain
    raw_values: tuple[object, ...]
    expected_value_count: int


@dataclass(frozen=True, kw_only=True)
class IntegerOrderingCase:
    """One integer ordering case that differs from lexicographic ordering."""

    description: str
    values: tuple[str, ...]
    expected_minimum: str
    expected_maximum: str


@dataclass(frozen=True, kw_only=True)
class IntervalOperationsTestCase:
    """Expected batch count for composed integer interval operations."""

    description: str
    start: int
    end: int
    step: int
    expected_batch_count: int
    expected_final_end: int


@dataclass(frozen=True, kw_only=True)
class TemporalSplitTestCase:
    """Expected calendar-aware temporal batch boundaries."""

    description: str
    grain: CursorGrain
    start: str
    end: str
    step: int
    expected_boundaries: tuple[str, ...]
