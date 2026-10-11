"""Assemble planner-ready compiled project objects."""

from __future__ import annotations

from collections.abc import Callable
from functools import partial
from pathlib import Path

import sqlbuild._native as _native
from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.compiler.compile._helpers.assembly.project import assemble_compiled_project
from sqlbuild.compiler.compile._helpers.diagnostics.collector import (
    with_collected_compile_diagnostics,
)
from sqlbuild.compiler.compile._helpers.explicit_references.checks import (
    explicit_reference_report,
)
from sqlbuild.compiler.compile.models import (
    PythonSqlReferenceReport,
)
from sqlbuild.compiler.compile.types import CompiledProjectView, CompileInputsView
from sqlbuild.compiler.compiled_project.main._record_model_analyses import record_model_analyses
from sqlbuild.compiler.compiled_project.main.project_with import project_with
from sqlbuild.compiler.lineage.types import ColumnLineageMode
from sqlbuild.compiler.macro_bridge.main.active_macro_bridge import active_macro_bridge
from sqlbuild.compiler.macro_bridge.main.run_with_macro_bridge import run_with_macro_bridge


@with_collected_compile_diagnostics
def assemble_project(
    *,
    inputs: CompileInputsView,
    inference_profile: ExpressionInferenceProfile | None = None,
    skip_column_inference: bool = False,
    column_lineage_mode: ColumnLineageMode = ColumnLineageMode.FAST,
    analysis_cache_dir: Path | None = None,
    analysis_model_names: frozenset[str] | None = None,
) -> CompiledProjectView:
    """Convert compile inputs into the planner-ready project view."""

    assemble: Callable[[], CompiledProjectView] = partial(
        assemble_compiled_project,
        inputs=inputs,
        inference_profile=inference_profile,
        skip_column_inference=skip_column_inference,
        column_lineage_mode=column_lineage_mode,
        analysis_cache_dir=analysis_cache_dir,
        analysis_model_names=analysis_model_names,
    )
    project: CompiledProjectView = _with_native_project(
        project=(
            run_with_macro_bridge(stage=assemble) if active_macro_bridge() is None else assemble()
        ),
        native_project=inputs.native_project,
    )
    references: PythonSqlReferenceReport = explicit_reference_report(
        project=project,
        discovered_inputs=inputs.discovered_inputs,
        enforce_explicit=inputs.project_config.references.enforce_explicit,
    )
    if not references.diagnostics and not references.unmatched:
        return project
    return project_with(
        project=project,
        diagnostics=(*project.diagnostics, *references.diagnostics),
        unmatched_literal_sql_relations=references.unmatched,
    )


def _with_native_project(
    *, project: CompiledProjectView, native_project: _native.NativeCompiledProject | None
) -> CompiledProjectView:
    """Hand the compile's native project the assembled analyses and keep it on the project."""

    if native_project is None:
        return project
    _ = record_model_analyses(project=native_project, models=project.models)
    if project.native_project is native_project:
        return project
    return project_with(project=project, native_project=native_project)
