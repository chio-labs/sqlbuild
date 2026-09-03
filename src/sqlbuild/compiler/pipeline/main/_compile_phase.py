"""Canonical project compilation phase."""

from __future__ import annotations

import time
from collections.abc import Callable

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.main.effective_config import build_effective_connection_config
from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline._helpers.analysis_selection import (
    resolve_compile_analysis_selection,
)
from sqlbuild.compiler.pipeline.main.compiled_project import build_compiled_project
from sqlbuild.compiler.pipeline.models import CompiledProjectPhaseResult, CompilePipelineOptions
from sqlbuild.diagnostics.classes.build_phase_timing_tracker import BuildPhaseTimingTracker


def compile_project_phase(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    options: CompilePipelineOptions | None = None,
    on_progress: Callable[[str], None] | None = None,
) -> CompiledProjectPhaseResult:
    """Compile a project without opening a warehouse planning connection."""

    resolved_options: CompilePipelineOptions = options or CompilePipelineOptions()
    effective_config: dict[str, object] = (
        resolved_options.connection_config
        if resolved_options.connection_config is not None
        else build_effective_connection_config(
            discovered_inputs=discovered_inputs,
            selected_target=resolved_options.selected_target,
            cli_vars=resolved_options.cli_vars,
        )
    )
    if on_progress is not None:
        on_progress("Compiling project...")
    compile_start: float = time.monotonic()
    try:
        project: CompiledProject = build_compiled_project(
            discovered_inputs=discovered_inputs,
            adapter=adapter,
            selected_target=resolved_options.selected_target,
            no_sql_validation=resolved_options.no_sql_validation,
            cli_vars=resolved_options.cli_vars,
            external_sql_reference_resolver=resolved_options.external_sql_reference_resolver,
            resolved_connection=effective_config,
            analysis_selection=resolve_compile_analysis_selection(
                options=resolved_options,
                discovered_inputs=discovered_inputs,
            ),
        )
    finally:
        compile_seconds: float = time.monotonic() - compile_start
        timing_tracker: BuildPhaseTimingTracker | None = BuildPhaseTimingTracker.current()
        if timing_tracker is not None:
            timing_tracker.compile_seconds = compile_seconds
    if on_progress is not None:
        on_progress(f"Compiled project. ({compile_seconds:.2f}s)")
    return CompiledProjectPhaseResult(
        project=project,
        connection_config=effective_config,
        compile_seconds=compile_seconds,
    )
