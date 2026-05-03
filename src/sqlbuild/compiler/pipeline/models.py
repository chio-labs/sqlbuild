"""Compiler pipeline models."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.planner.models import PlanOutput


@dataclass(frozen=True)
class CompilePipelineResult:
    """Complete output from the compile-and-plan pipeline."""

    project: CompiledProject
    plan_output: PlanOutput
    manifest: dict[str, object] = field(default_factory=dict)
