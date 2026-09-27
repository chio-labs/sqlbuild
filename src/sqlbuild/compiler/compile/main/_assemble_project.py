"""Assemble planner-ready compiled project objects."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.compiler.compile._helpers.assembly.audit_gates import validate_attached_audit_gates
from sqlbuild.compiler.compile._helpers.assembly.project import assemble_compiled_project
from sqlbuild.compiler.compile._helpers.explicit_references.hook_reads import validate_hook_reads
from sqlbuild.compiler.compile._helpers.explicit_references.python_sql import (
    validate_python_sql_references,
)
from sqlbuild.compiler.compile.models import (
    CompiledProject,
    CompileProjectInputs,
)
from sqlbuild.compiler.lineage.types import ColumnLineageMode


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
    validate_attached_audit_gates(project=project)
    validate_hook_reads(project=project)
    if inputs.project_config.references.enforce_explicit:
        validate_python_sql_references(project=project, discovered_inputs=inputs.discovered_inputs)
    return project
