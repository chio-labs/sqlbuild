"""Test case types for plan formatter tests."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlbuild.compiler.planner.models import (
    PlanOutput,
)


@dataclass(frozen=True)
class FormatPlanTestCase:
    description: str
    plan_output: PlanOutput
    full_refresh: bool = False
    expected_fragments: tuple[str, ...] = field(default_factory=tuple)
    unexpected_fragments: tuple[str, ...] = field(default_factory=tuple)
