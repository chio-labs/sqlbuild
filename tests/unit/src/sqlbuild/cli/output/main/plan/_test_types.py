"""Test case types for plan formatter tests."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlbuild.compiler.pipeline.models import PythonPlanEntry
from sqlbuild.compiler.planner.models import (
    PlanOutput,
)
from sqlbuild.presentation.models import DisplayOptions


@dataclass(frozen=True)
class FormatPlanTestCase:
    description: str
    plan_output: PlanOutput
    full_refresh: bool = False
    display_options: DisplayOptions | None = None
    include_standard_freshness_diagnostics: bool = True
    python_plan_entries: tuple[PythonPlanEntry, ...] = field(default_factory=tuple)
    expected_fragments: tuple[str, ...] = field(default_factory=tuple)
    unexpected_fragments: tuple[str, ...] = field(default_factory=tuple)
    expected_ordered_fragments: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class FormatPlanColorTestCase:
    description: str
    plan_output: PlanOutput
    expected_fragments: tuple[str, ...]
    python_plan_entries: tuple[PythonPlanEntry, ...] = field(default_factory=tuple)
