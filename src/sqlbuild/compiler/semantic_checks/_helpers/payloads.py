"""Plain-data payloads of compiled facts for the native semantic completion requests."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import (
    CompiledLineageColumnFact,
    CompiledModel,
    CompiledProject,
    CompilerDiagnostic,
)
from sqlbuild.compiler.sql_analysis.models import SqlBindingDiagnostic


def lineage_payload(model: CompiledModel) -> list[tuple[str, list[tuple[str, str]]]]:
    """Each output column with the `(resource, column)` pairs it reads."""

    return [_output_payload(output) for output in model.fast_lineage_columns or ()]


def _output_payload(output: CompiledLineageColumnFact) -> tuple[str, list[tuple[str, str]]]:
    return (
        output.output_column,
        [(source.resource_name, source.column_name) for source in output.upstream_columns],
    )


def diagnostic_ids(project: CompiledProject) -> dict[CompilerDiagnostic, int]:
    """One id per distinct diagnostic value, as Python's value-keyed dicts and sets see them."""

    ids: dict[CompilerDiagnostic, int] = {}
    for item in project.diagnostics:
        _ = ids.setdefault(item, len(ids))
    for model in project.models:
        for item in model.binding_diagnostics:
            _ = ids.setdefault(item, len(ids))
    return ids


def raw_binding_ids(
    binding_results: dict[str, tuple[SqlBindingDiagnostic, ...]],
) -> dict[SqlBindingDiagnostic, int]:
    """One id per distinct raw binding row value."""

    ids: dict[SqlBindingDiagnostic, int] = {}
    for rows in binding_results.values():
        for row in rows:
            _ = ids.setdefault(row, len(ids))
    return ids


def has_blocking_binding(project: CompiledProject) -> bool:
    """Whether any model owns a binding error, without which type recovery changes nothing."""

    for model in project.models:
        for item in model.binding_diagnostics:
            if item.is_error:
                return True
    return False
