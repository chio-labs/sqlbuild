"""Assemble planner-ready compiled project objects."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.compiler.compile._helpers.assembly.audit_gates import (
    attached_audit_gate_diagnostics,
)
from sqlbuild.compiler.compile._helpers.assembly.project import assemble_compiled_project
from sqlbuild.compiler.compile._helpers.diagnostics.collector import (
    with_collected_compile_diagnostics,
)
from sqlbuild.compiler.compile._helpers.explicit_references.hook_reads import hook_read_diagnostics
from sqlbuild.compiler.compile._helpers.explicit_references.python_sql import (
    python_sql_reference_diagnostics,
)
from sqlbuild.compiler.compile.models import (
    CompiledProject,
    CompileProjectInputs,
    CompilerDiagnostic,
    PythonSqlReferenceReport,
)
from sqlbuild.compiler.lineage.types import ColumnLineageMode


@with_collected_compile_diagnostics
def assemble_project(
    *,
    inputs: CompileProjectInputs,
    inference_profile: ExpressionInferenceProfile | None = None,
    skip_column_inference: bool = False,
    column_lineage_mode: ColumnLineageMode = ColumnLineageMode.FAST,
    analysis_cache_dir: Path | None = None,
    analysis_model_names: frozenset[str] | None = None,
) -> CompiledProject:
    """Convert compile inputs into the planner-ready project view."""

    project: CompiledProject = assemble_compiled_project(
        inputs=inputs,
        inference_profile=inference_profile,
        skip_column_inference=skip_column_inference,
        column_lineage_mode=column_lineage_mode,
        analysis_cache_dir=analysis_cache_dir,
        analysis_model_names=analysis_model_names,
    )
    python_sql: PythonSqlReferenceReport = (
        python_sql_reference_diagnostics(
            project=project, discovered_inputs=inputs.discovered_inputs
        )
        if inputs.project_config.references.enforce_explicit
        else PythonSqlReferenceReport()
    )
    reference_diagnostics: tuple[CompilerDiagnostic, ...] = (
        *attached_audit_gate_diagnostics(project=project),
        *hook_read_diagnostics(project=project),
        *python_sql.diagnostics,
    )
    if not reference_diagnostics and not python_sql.unmatched:
        return project
    return replace(
        project,
        diagnostics=(*project.diagnostics, *reference_diagnostics),
        unmatched_literal_sql_relations=python_sql.unmatched,
    )
