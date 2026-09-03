"""Public compile-only pipeline entrypoint."""

from __future__ import annotations

from collections.abc import Callable

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main._compile_phase import compile_project_phase
from sqlbuild.compiler.pipeline.models import (
    CompiledProjectPhaseResult,
    CompilePipelineOptions,
    CompilePipelineResult,
)
from sqlbuild.compiler.planner.models import PlanOutput


def run_compile_only_pipeline(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    options: CompilePipelineOptions,
    on_progress: Callable[[str], None] | None = None,
) -> CompilePipelineResult:
    """Compile a project for consumers that construct their own focused plans."""

    compiled: CompiledProjectPhaseResult = compile_project_phase(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        options=options,
        on_progress=on_progress,
    )
    return CompilePipelineResult(
        project=compiled.project,
        plan_output=PlanOutput(),
        compile_seconds=compiled.compile_seconds,
        planning_seconds=0.0,
    )
