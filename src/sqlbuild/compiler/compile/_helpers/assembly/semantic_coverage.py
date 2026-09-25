"""Explain the limits of offline semantic checks without per-model warnings."""

from __future__ import annotations

from sqlbuild.compiler.compile._helpers.assembly.semantic_shapes import semantic_shapes
from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.references.types import SqlReferenceKind
from sqlbuild.compiler.sql_analysis.constants import TYPE_CHECKED_DIALECTS


def semantic_coverage(project: CompiledProject) -> dict[str, tuple[str, ...]]:
    """Return partial-check reasons for machine reports."""

    if not project.settings.sql_analysis:
        return {}
    shapes: dict[str, dict[str, str]] = semantic_shapes(project=project)
    invalid: set[str] = set()
    for model in project.models:
        if any(item.is_error for item in model.binding_diagnostics):
            invalid.add(model.name)
    blocked_by: dict[str, set[str]] = {name: {name} for name in invalid}
    if invalid:
        for _ in project.models:
            changed: bool = False
            for model in project.models:
                causes: set[str] = set(blocked_by.get(model.name, ()))
                for reference in model.references:
                    causes.update(blocked_by.get(reference.ref_name, ()))
                if causes and causes != blocked_by.get(model.name):
                    blocked_by[model.name] = causes
                    changed = True
            if not changed:
                break
    reasons: dict[str, tuple[str, ...]] = {}
    for model in project.models:
        if model.config.values.get("sql_analysis") is False:
            reasons[model.name] = ("SQL analysis disabled",)
            continue
        partial: list[str] = [
            f"open source: {reference.ref_name}"
            if reference.ref_kind == SqlReferenceKind.SOURCE
            else f"open input: {reference.ref_name}"
            for reference in model.references
            if reference.ref_kind
            in {SqlReferenceKind.SOURCE, SqlReferenceKind.REF, SqlReferenceKind.DBT_REF}
            and reference.ref_name not in shapes
        ]
        partial.extend(
            f"depends on invalid model {name}"
            for name in sorted(blocked_by.get(model.name, set()) - {model.name})
        )
        if not model.inferred_columns:
            partial.append("output shape could not be inferred")
        elif model.fast_lineage_has_star and model.name not in shapes:
            partial.append("unresolved star over open inputs")
        if any(column.type is None for column in model.inferred_columns or ()):
            partial.append("some output types are unknown")
        if (project.sql_analysis_dialect or "generic") not in TYPE_CHECKED_DIALECTS:
            partial.append("type checking awaits dialect coercion support")
        if partial:
            reasons[model.name] = tuple(sorted(set(partial)))
    return reasons
