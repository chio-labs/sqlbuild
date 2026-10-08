"""The native semantic completion stage: type recovery, metadata checks, then completion."""

from __future__ import annotations

from dataclasses import replace

from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.compiler.compile.classes.semantic_completion_inputs import SemanticCompletionInputs
from sqlbuild.compiler.compile.models import CompiledProject, CompilerDiagnostic
from sqlbuild.compiler.semantic_checks._helpers.completion import complete_native_diagnostics
from sqlbuild.compiler.semantic_checks._helpers.deferrals import record_semantic_deferral
from sqlbuild.compiler.semantic_checks._helpers.type_recovery import recover_native_output_types
from sqlbuild.compiler.semantic_checks.constants import (
    COMPLETION_DEFERRAL_SITE,
    METADATA_DEFERRAL_SITE,
    NATIVE_SEMANTIC_METADATA_CHECKS,
    NATIVE_SEMANTIC_NO_CATALOG,
)
from sqlbuild.compiler.sql_analysis.models import SqlBindingDiagnostic


def completed_semantic_project(
    *,
    project: CompiledProject,
    profile: ExpressionInferenceProfile,
    binding_results: dict[str, tuple[SqlBindingDiagnostic, ...]],
    resource_sql_analysis: bool,
) -> CompiledProject | None:
    """Python's completed project, or None where any native step hands the stage back."""

    if project.binding_catalog is None:
        record_semantic_deferral(kind=NATIVE_SEMANTIC_NO_CATALOG, site=COMPLETION_DEFERRAL_SITE)
        return None
    catalog: object = project.binding_catalog.native
    recovered: CompiledProject | None = recover_native_output_types(
        project=project, binding_results=binding_results, catalog=catalog
    )
    if recovered is None:
        return None
    if recovered.settings.sql_analysis:
        record_semantic_deferral(kind=NATIVE_SEMANTIC_METADATA_CHECKS, site=METADATA_DEFERRAL_SITE)
    metadata: tuple[CompilerDiagnostic, ...] = SemanticCompletionInputs.metadata_diagnostics(
        project=recovered, profile=profile, resource_sql_analysis=resource_sql_analysis
    )
    return complete_native_diagnostics(
        project=replace(recovered, diagnostics=(*recovered.diagnostics, *metadata)),
        catalog=catalog,
    )
