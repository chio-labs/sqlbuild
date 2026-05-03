"""Compiler pipeline models."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.planner.models import ModelPlanEntry, PlanOutput, SeedPlanEntry


@dataclass(frozen=True)
class CompilePipelineResult:
    """Complete output from the compile-and-plan pipeline."""

    project: CompiledProject
    plan_output: PlanOutput
    manifest: dict[str, object] = field(default_factory=dict)
    custom_materializations: dict[str, Callable[..., Any]] = field(default_factory=dict)


@dataclass(frozen=True)
class ClonePipelineResult:
    """Prepared clone inputs for source and target environments."""

    source_project: CompiledProject
    target_project: CompiledProject
    clone_plan: PlanOutput
    target_model_entries: tuple[ModelPlanEntry, ...] = field(default_factory=tuple)
    target_seed_entries: tuple[SeedPlanEntry, ...] = field(default_factory=tuple)
    source_model_entries: tuple[ModelPlanEntry, ...] = field(default_factory=tuple)
    source_seed_entries: tuple[SeedPlanEntry, ...] = field(default_factory=tuple)
