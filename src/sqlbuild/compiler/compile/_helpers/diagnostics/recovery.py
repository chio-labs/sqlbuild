"""Recover poisoned output names without suppressing unrelated downstream errors."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import replace

from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.compiler.compile._helpers.assembly.metadata_validation import (
    get_semantic_metadata_diagnostics,
)
from sqlbuild.compiler.compile._helpers.assembly.semantic_shapes import semantic_shapes
from sqlbuild.compiler.compile._helpers.diagnostics.details import (
    closest_column,
    explain_diagnostics,
    missing_column,
    unaliased_output_columns,
    update_binding_models,
)
from sqlbuild.compiler.compile._helpers.diagnostics.sql_analysis_opt_outs import (
    reject_unneeded_sql_analysis_opt_outs,
)
from sqlbuild.compiler.compile._helpers.diagnostics.type_recovery import recover_output_types
from sqlbuild.compiler.compile.models import (
    CompiledModel,
    CompiledProject,
    CompilerDiagnostic,
)
from sqlbuild.compiler.sql_analysis.models import SqlBindingDiagnostic

_MISSING_CODE: str = "B002"
_TEST_CODE: str = "B302"


def complete_semantic_diagnostics(
    *,
    project: CompiledProject,
    profile: ExpressionInferenceProfile,
    binding_results: dict[str, tuple[SqlBindingDiagnostic, ...]],
    resource_sql_analysis: bool = True,
) -> CompiledProject:
    """Recover type facts before metadata checks, then explain retained root diagnostics."""
    project = recover_output_types(project=project, binding_results=binding_results)
    project = replace(
        project,
        diagnostics=(
            *project.diagnostics,
            *get_semantic_metadata_diagnostics(
                project=project, profile=profile, resource_sql_analysis=resource_sql_analysis
            ),
        ),
    )
    return reject_unneeded_sql_analysis_opt_outs(explain_diagnostics(recover_diagnostics(project)))


def recover_diagnostics(project: CompiledProject) -> CompiledProject:
    """Recover poisoned uses while retaining independent errors on unaffected outputs."""
    roots: list[CompilerDiagnostic] = [
        item for item in project.diagnostics if item.code == _MISSING_CODE
    ]
    if not roots:
        return project
    shapes: dict[str, dict[str, str]] = semantic_shapes(project=project)
    models: dict[str, CompiledModel] = {model.name: model for model in project.models}
    poisoned: dict[tuple[str, str], CompilerDiagnostic] = {}
    origins: dict[CompilerDiagnostic, tuple[str, str]] = {}
    projections: dict[str, set[str]] = {}
    inferred_names: dict[str, set[str]] = {}
    upstream_sources: dict[str, dict[str, set[tuple[str, str]]]] = {}
    for diagnostic in roots:
        model: CompiledModel | None = models.get(diagnostic.resource_name or "")
        missing: tuple[str, str | None] | None = missing_column(diagnostic.message)
        if model is None or missing is None:
            continue
        column, table = missing
        if model.name not in inferred_names:
            inferred_names[model.name] = {item.name for item in model.inferred_columns or ()}
        if column not in inferred_names[model.name]:
            continue
        if model.name not in projections:
            projections[model.name] = unaliased_output_columns(
                model=model, dialect=project.sql_analysis_dialect
            )
        if column not in projections[model.name]:
            continue
        if model.name not in upstream_sources:
            upstream_sources[model.name] = _upstream_sources_by_output(model=model)
        if table is None or (table, column) not in upstream_sources[model.name].get(column, set()):
            continue
        suggestion: str | None = closest_column(name=column, columns=shapes.get(table or "", {}))
        if suggestion is not None:
            poisoned[(model.name, suggestion)] = diagnostic
            origins[diagnostic] = model.name, suggestion
    for _ in project.models:
        previous: int = len(poisoned)
        for model in project.models:
            for column in model.fast_lineage_columns or ():
                for source in column.upstream_columns:
                    root: CompilerDiagnostic | None = poisoned.get(
                        (source.resource_name, source.column_name)
                    )
                    if root is not None:
                        poisoned.setdefault((model.name, column.output_column), root)
        if len(poisoned) == previous:
            break
    skipped: Counter[tuple[CompilerDiagnostic, str, str]] = Counter()
    kept: list[CompilerDiagnostic] = []
    for diagnostic in project.diagnostics:
        missing = missing_column(diagnostic.message) if diagnostic.code == _MISSING_CODE else None
        target: tuple[str, str] | None = (
            (missing[1], missing[0]) if missing and missing[1] else None
        )
        if diagnostic.code == _TEST_CODE:
            match: re.Match[str] | None = re.search(
                r"'__(?:expected|ref)__(.+)' names unknown column '([^']+)'", diagnostic.message
            )
            if match:
                target = match.group(1), match.group(2)
        root = poisoned.get(target) if target is not None else None
        if root is not None and root != diagnostic and target is not None:
            skipped[(root, *origins[root])] += 1
        else:
            kept.append(diagnostic)
    notes: dict[CompilerDiagnostic, list[str]] = {}
    for (root, model_name, column_name), count in skipped.items():
        notes.setdefault(root, []).append(
            f"{count} downstream uses of {model_name}.{column_name} "
            "were not checked because of this error"
        )
    diagnostics: tuple[CompilerDiagnostic, ...] = tuple(
        replace(item, notes=(*item.notes, *notes.get(item, ()))) for item in kept
    )
    return replace(
        project,
        diagnostics=diagnostics,
        models=update_binding_models(models=project.models, diagnostics=diagnostics),
    )


def _upstream_sources_by_output(*, model: CompiledModel) -> dict[str, set[tuple[str, str]]]:
    sources: dict[str, set[tuple[str, str]]] = {}
    for output in model.fast_lineage_columns or ():
        sources.setdefault(output.output_column, set()).update(
            (source.resource_name, source.column_name) for source in output.upstream_columns
        )
    return sources
