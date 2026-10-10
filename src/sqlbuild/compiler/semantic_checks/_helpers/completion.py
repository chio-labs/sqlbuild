"""Native diagnostic recovery, explanations and opt-out rejection after the metadata checks."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import sqlbuild._native as _native
from sqlbuild.compiler.compile.classes.semantic_completion_inputs import SemanticCompletionInputs
from sqlbuild.compiler.compile.constants import UNNEEDED_SQL_ANALYSIS_OPT_OUT_CODE
from sqlbuild.compiler.compile.models import CompiledModel, CompiledProject, CompilerDiagnostic
from sqlbuild.compiler.compile.types import (
    CompiledResourceType,
    DiagnosticPhase,
    DiagnosticSeverity,
)
from sqlbuild.compiler.semantic_checks._helpers.payloads import diagnostic_ids, lineage_payload
from sqlbuild.spec.contracts.models import SourceLocation

_RECOVERED_CODE: str = "B002"

type _Location = tuple[int, int, int | None, int | None]
type _Completed = tuple[
    int, str, str | None, list[str], _Location | None, int | None, int | None, bool
]


def complete_native_diagnostics(
    *,
    project: CompiledProject,
    catalog: object,
    session: Any | None,
    session_models: frozenset[str],
) -> CompiledProject:
    """The recovered, explained and opt-out-checked project; a native internal failure raises."""

    ids: dict[CompilerDiagnostic, int] = diagnostic_ids(project)
    recovers: bool = any(item.code == _RECOVERED_CODE for item in project.diagnostics)
    shapes: dict[str, dict[str, str]] = (
        SemanticCompletionInputs.shapes(project) if project.diagnostics else {}
    )
    request: Any = (
        project.sql_analysis_dialect,
        [_diagnostic_payload(item=item, ids=ids) for item in project.diagnostics],
        [
            _model_payload(model=model, lineage=recovers, from_session=model.name in session_models)
            for model in project.models
        ],
        [(name, list(columns.items())) for name, columns in shapes.items()],
    )
    completed, model_bindings, order = _native.complete_semantic_checks(catalog, request, session)
    diagnostics: list[CompilerDiagnostic] = [
        _completed(original=project.diagnostics[row[0]], row=row) for row in completed
    ]
    models: tuple[CompiledModel, ...] = project.models
    if model_bindings is not None:
        models = tuple(
            replace(
                model, binding_diagnostics=_positions(diagnostics=diagnostics, positions=positions)
            )
            for model, positions in zip(project.models, model_bindings, strict=True)
        )
    final: list[CompilerDiagnostic] = []
    for position, opt_out in order:
        if position is not None:
            final.append(diagnostics[position])
        elif opt_out is not None:
            index, message, note, help_text = opt_out
            final.append(
                _opt_out(
                    model=project.models[index], message=message, note=note, help_text=help_text
                )
            )
    return replace(project, models=models, diagnostics=tuple(final))


def _positions(
    *, diagnostics: list[CompilerDiagnostic], positions: list[int]
) -> tuple[CompilerDiagnostic, ...]:
    return tuple(diagnostics[position] for position in positions)


def _diagnostic_payload(
    *, item: CompilerDiagnostic, ids: dict[CompilerDiagnostic, int]
) -> tuple[Any, ...]:
    location: SourceLocation | None = item.location
    return (
        ids[item],
        item.code,
        item.message,
        None if item.resource_type is None else str(item.resource_type),
        item.resource_name,
        item.line,
        item.column,
        None
        if location is None
        else (location.line, location.column, location.end_line, location.end_column),
        item.help,
        list(item.notes),
    )


def _model_payload(*, model: CompiledModel, lineage: bool, from_session: bool) -> tuple[Any, ...]:
    opt_out: SourceLocation | None = model.rejected_sql_analysis_opt_out
    return (
        model.name,
        model.query_sql,
        model.authored_sql,
        None if from_session else [column.name for column in model.inferred_columns or ()],
        _lineage(model=model, lineage=lineage, from_session=from_session),
        [item.code for item in model.binding_diagnostics],
        None if opt_out is None else opt_out.path.name,
    )


def _completed(*, original: CompilerDiagnostic, row: _Completed) -> CompilerDiagnostic:
    _, message, help_text, notes, location, line, column, changed = row
    if not changed:
        return original
    current: SourceLocation | None = original.location
    if current is not None and location is not None:
        line_number, column_number, end_line, end_column = location
        if (current.line, current.column, current.end_line, current.end_column) != location:
            current = replace(
                current,
                line=line_number,
                column=column_number,
                end_line=end_line,
                end_column=end_column,
            )
    return replace(
        original,
        message=message,
        help=help_text,
        notes=tuple(notes),
        location=current,
        line=line,
        column=column,
    )


def _opt_out(
    *, model: CompiledModel, message: str, note: str, help_text: str
) -> CompilerDiagnostic:
    return CompilerDiagnostic(
        phase=DiagnosticPhase.COMPILE,
        severity=DiagnosticSeverity.ERROR,
        code=UNNEEDED_SQL_ANALYSIS_OPT_OUT_CODE,
        message=message,
        resource_type=CompiledResourceType.MODEL,
        resource_name=model.name,
        location=model.rejected_sql_analysis_opt_out,
        notes=(note,),
        help=help_text,
    )


def _lineage(
    *, model: CompiledModel, lineage: bool, from_session: bool
) -> list[tuple[str, list[tuple[str, str]]]] | None:
    """The model's lineage rows; None asks for the session's, and only recovery reads them."""

    if not lineage:
        return []
    if from_session:
        return None
    return lineage_payload(model)
