"""Virtual executor result models."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from sqlbuild.compiler.compile.models.core import CompiledProject
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.executor.build.models import BuildExecutionResult
from sqlbuild.shared.types import ExecutionResourceKind


@dataclass(frozen=True)
class VirtualBuildExecutionHooks:
    """Callbacks to use once a virtual build plan is ready."""

    on_node_start: Callable[[str, ExecutionResourceKind], None] | None = None
    on_node_complete: Callable[[object], None] | None = None
    on_sub_progress: Callable[[str], None] | None = None


@dataclass(frozen=True)
class VirtualBuildPipelineResult:
    """Result returned by the virtual build pipeline."""

    project: CompiledProject
    plan_output: PlanOutput
    execution_result: BuildExecutionResult
