"""Selection policy for deep model SQL analysis."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import CompileAnalysisSelection
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.models import CompilePipelineOptions


def resolve_compile_analysis_selection(
    *,
    options: CompilePipelineOptions,
    discovered_inputs: DiscoveredProjectInputs,
) -> CompileAnalysisSelection | None:
    """Limit analysis when selectors cannot resolve through Python graph nodes."""

    has_python_nodes: bool = bool(
        discovered_inputs.loader_functions
        or discovered_inputs.task_functions
        or discovered_inputs.asset_functions
        or discovered_inputs.check_functions
    )
    if options.resolve_python_run_selectors and has_python_nodes:
        return None
    return CompileAnalysisSelection(
        select=options.select,
        exclude=options.exclude,
        auto_load_sources=options.auto_load_sources,
    )
