"""Native output-type recovery, with Python's revalidation on the compile's binding catalog."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import sqlbuild._native as _native
from sqlbuild.compiler.compile.classes.semantic_completion_inputs import SemanticCompletionInputs
from sqlbuild.compiler.compile.models import (
    CompiledModel,
    CompiledProject,
    CompilerDiagnostic,
    InferredColumn,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.semantic_checks._helpers.payloads import (
    diagnostic_ids,
    has_blocking_binding,
    lineage_payload,
    raw_binding_ids,
)
from sqlbuild.compiler.semantic_checks.constants import (
    NATIVE_TYPE_RECOVERY_UNCHANGED,
    UNKNOWN_RECOVERED_TYPE,
)
from sqlbuild.compiler.sql_analysis.main._schema_validation import get_schema_validations
from sqlbuild.compiler.sql_analysis.models import SqlBindingDiagnostic, SqlBindingResult

type _Revised = list[tuple[str, int | None, int | None]]


def recover_native_output_types(
    *,
    project: CompiledProject,
    binding_results: dict[str, tuple[SqlBindingDiagnostic, ...]],
    catalog: object,
    session: Any | None,
    session_models: frozenset[str],
) -> CompiledProject:
    """The project with recovered output types; a native internal failure raises."""

    if not has_blocking_binding(project):
        return project
    ids: dict[CompilerDiagnostic, int] = diagnostic_ids(project)
    raw_ids: dict[SqlBindingDiagnostic, int] = raw_binding_ids(binding_results)
    request: Any = (
        project.sql_analysis_dialect,
        [
            _model_payload(
                model=model,
                binding_results=binding_results,
                ids=ids,
                raw_ids=raw_ids,
                from_session=model.name in session_models,
            )
            for model in project.models
        ],
        [
            (
                ids[item],
                item.code,
                item.resource_type == CompiledResourceType.MODEL,
                item.resource_name,
            )
            for item in project.diagnostics
        ],
    )
    recovery: _native.SemanticTypeRecovery = _native.plan_semantic_type_recovery(
        catalog, request, session
    )
    if recovery.status == NATIVE_TYPE_RECOVERY_UNCHANGED:
        return project
    poisoned: list[tuple[str, str]] = recovery.poisoned
    outcome: tuple[list[tuple[int, str | None]], list[list[int]]] = recovery.finish(
        _revalidated(project=project, revalidated=recovery.revalidated, poisoned=poisoned)
    )
    kept, model_bindings = outcome
    diagnostics: tuple[CompilerDiagnostic, ...] = tuple(
        _with_note(diagnostic=project.diagnostics[index], note=note) for index, note in kept
    )
    poisoned_outputs: frozenset[tuple[str, str]] = frozenset(poisoned)
    models: tuple[CompiledModel, ...] = tuple(
        _recovered_model(
            model=model,
            bindings=_positions(diagnostics=diagnostics, positions=positions),
            poisoned=poisoned_outputs,
        )
        for model, positions in zip(project.models, model_bindings, strict=True)
    )
    return replace(project, models=models, diagnostics=diagnostics)


def _revalidated(
    *, project: CompiledProject, revalidated: list[int], poisoned: list[tuple[str, str]]
) -> list[_Revised]:
    """Python's revalidation of each planned model with unknown types for poisoned outputs."""

    if not revalidated:
        return []
    shapes: dict[str, dict[str, str]] = _unknown_shapes(
        shapes=SemanticCompletionInputs.shapes(project), poisoned=poisoned
    )
    revised: list[_Revised] = []
    for index in revalidated:
        result: SqlBindingResult = get_schema_validations(
            requests=(
                SemanticCompletionInputs.revalidation_request(
                    project=project, model=project.models[index], shapes=shapes
                ),
            )
        )[0]
        revised.append([(item.code, item.start, item.end) for item in result.diagnostics])
    return revised


def _model_payload(
    *,
    model: CompiledModel,
    binding_results: dict[str, tuple[SqlBindingDiagnostic, ...]],
    ids: dict[CompilerDiagnostic, int],
    raw_ids: dict[SqlBindingDiagnostic, int],
    from_session: bool,
) -> tuple[Any, ...]:
    raws: tuple[SqlBindingDiagnostic, ...] = (
        binding_results.get(model.name, ()) if model.binding_diagnostics else ()
    )
    return (
        model.name,
        model.query_sql,
        None
        if from_session or model.inferred_columns is None
        else [column.name for column in model.inferred_columns],
        [reference.ref_name for reference in model.references],
        None if from_session else lineage_payload(model),
        [(ids[item], item.code, item.message, item.is_error) for item in model.binding_diagnostics],
        [(raw_ids[raw], raw.code, raw.message, raw.start, raw.end) for raw in raws],
    )


def _with_note(*, diagnostic: CompilerDiagnostic, note: str | None) -> CompilerDiagnostic:
    return replace(diagnostic, notes=(*diagnostic.notes, *((note,) if note is not None else ())))


def _positions(
    *, diagnostics: tuple[CompilerDiagnostic, ...], positions: list[int]
) -> tuple[CompilerDiagnostic, ...]:
    return tuple(diagnostics[position] for position in positions)


def _recovered_model(
    *,
    model: CompiledModel,
    bindings: tuple[CompilerDiagnostic, ...],
    poisoned: frozenset[tuple[str, str]],
) -> CompiledModel:
    columns: tuple[InferredColumn, ...] | None = None
    if model.inferred_columns is not None:
        columns = tuple(
            replace(column, type=None) if (model.name, column.name) in poisoned else column
            for column in model.inferred_columns
        )
    unchecked: frozenset[str] = frozenset(column for name, column in poisoned if name == model.name)
    return replace(
        model,
        binding_diagnostics=bindings,
        inferred_columns=columns,
        unchecked_output_columns=unchecked,
    )


def _unknown_shapes(
    *, shapes: dict[str, dict[str, str]], poisoned: list[tuple[str, str]]
) -> dict[str, dict[str, str]]:
    unknown: dict[str, dict[str, str]] = {name: dict(columns) for name, columns in shapes.items()}
    for name, column in poisoned:
        if name in unknown and column in unknown[name]:
            unknown[name][column] = UNKNOWN_RECOVERED_TYPE
    return unknown
