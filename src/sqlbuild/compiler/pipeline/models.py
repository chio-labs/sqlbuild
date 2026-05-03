"""Compiler pipeline models."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.planner.models import PlanOutput


@dataclass(frozen=True)
class CompilePipelineResult:
    """Complete output from the compile-and-plan pipeline."""

    project: CompiledProject
    plan_output: PlanOutput
    manifest: dict[str, object] = field(default_factory=dict)
    custom_materializations: dict[str, Callable[..., Any]] = field(default_factory=dict)
