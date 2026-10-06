"""Selection policies applied to compile pipeline options."""

from __future__ import annotations

from dataclasses import replace

from sqlbuild.compiler.compile.models import (
    CompileAnalysisSelection,
    CompiledObjectKey,
    CompiledProject,
)
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.models import CompilePipelineOptions
from sqlbuild.compiler.planner.main.selection._resolve_planner_scopes import (
    resolve_planner_scopes,
)
from sqlbuild.compiler.planner.main.selection._split_unit_test_selectors import (
    split_project_unit_test_selectors,
)
from sqlbuild.compiler.planner.models import (
    PlannerPolicies,
    PlannerScopeResolution,
    PlannerSelection,
    UnitTestSelectorSplit,
)


def apply_unit_test_selectors(
    *, options: CompilePipelineOptions | None, discovered_inputs: DiscoveredProjectInputs
) -> CompilePipelineOptions:
    """Return options whose selectors name only resources, with unit tests selected apart."""

    resolved: CompilePipelineOptions = options if options is not None else CompilePipelineOptions()
    if not resolved.select and not resolved.exclude:
        return resolved
    split: UnitTestSelectorSplit = split_project_unit_test_selectors(
        select=resolved.select,
        exclude=resolved.exclude,
        discovered_inputs=discovered_inputs,
        accepts_unit_tests=resolved.accepts_unit_test_selectors,
    )
    return replace(
        resolved,
        select=split.select,
        exclude=split.exclude,
        sql_test_selection=split.sql_test_selection,
    )


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
    if (
        options.resolve_python_run_selectors and has_python_nodes
    ) or options.sql_test_selection.names:
        return CompileAnalysisSelection(no_cache=options.no_cache)
    return CompileAnalysisSelection(
        select=options.select,
        exclude=options.exclude,
        auto_load_sources=options.auto_load_sources,
        no_cache=options.no_cache,
    )


def resolve_configured_rule_selection(
    *,
    options: CompilePipelineOptions,
    discovered_inputs: DiscoveredProjectInputs,
    project: CompiledProject,
) -> frozenset[CompiledObjectKey] | None:
    """Align configured-rule subjects with models that received deep SQL analysis."""

    if not options.sql_test_selection.models_selected:
        return frozenset()
    analysis_selection: CompileAnalysisSelection | None = resolve_compile_analysis_selection(
        options=options,
        discovered_inputs=discovered_inputs,
    )
    if analysis_selection is None or (
        not analysis_selection.select and not analysis_selection.exclude
    ):
        return None
    scopes: PlannerScopeResolution = resolve_planner_scopes(
        project=project,
        selection=PlannerSelection(
            select=analysis_selection.select,
            exclude=analysis_selection.exclude,
        ),
        policies=PlannerPolicies(auto_load_sources=analysis_selection.auto_load_sources),
    )
    return frozenset(model.key for model in scopes.stale_warning_scope.models_by_name.values())
