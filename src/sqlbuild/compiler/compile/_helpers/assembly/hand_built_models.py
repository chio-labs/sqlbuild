"""Explicit boundary conversion of a hand-built model input's native analysis."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import sqlbuild._native as _native
from sqlbuild.compiler.analysis_session.main._dynamic_contract_proof import dynamic_contract_proof
from sqlbuild.compiler.analysis_session.main._session_outcome_analysis import (
    session_outcome_analysis,
)
from sqlbuild.compiler.compile._helpers.assembly.targets import build_model_relation_target
from sqlbuild.compiler.compile.models import (
    CompiledLineageColumnFact,
    CompiledModel,
    CompiledObjectKey,
    CompiledSqlExpansion,
    CompilerDiagnostic,
    DynamicColumnContractProof,
    ExpansionSpan,
    HandBuiltAnalysis,
    InferredColumn,
    ModelSqlAnalysis,
    PolyglotAnalysisResult,
)
from sqlbuild.compiler.compile.types import (
    CompiledResourceType,
    DiagnosticPhase,
    ModelInput,
)
from sqlbuild.compiler.lineage.types import InferredNullability
from sqlbuild.compiler.sql_analysis.models import SqlBindingDiagnostic
from sqlbuild.spec.contracts.models import SourceLocation


def hand_built_compiled_model(
    *,
    model_input: ModelInput,
    deps: list[tuple[str, str]],
    analysis: HandBuiltAnalysis,
    macro_deps: tuple[str, ...],
) -> CompiledModel:
    """A `CompiledModel` for a model input built outside the native compile-input stage."""

    model_name: str = model_input.model_file.file_path.stem
    inferred: tuple[InferredColumn, ...] | None = None
    lineage: Sequence[CompiledLineageColumnFact] | None = None
    has_star: bool = False
    star_resolved: bool = False
    diagnostics: tuple[CompilerDiagnostic, ...] = ()
    validated: bool = False
    proof: DynamicColumnContractProof | None = dynamic_contract_proof(analysis.standalone_proof)
    if analysis.session is not None:
        session, position = analysis.session
        outcome: ModelSqlAnalysis = session_outcome_analysis(
            session=session, position=position, placeholders=None
        )
        result: PolyglotAnalysisResult = outcome.polyglot_analysis
        if result.analysis_succeeded:
            inferred = result.columns
            lineage = result.lineage_columns
            has_star, star_resolved = result.has_star, result.star_resolved
        else:
            inferred = dynamic_fallback_columns(analysis.fallback)
        proof = outcome.dynamic_column_contract or proof
        validated = result.binding_validated
        diagnostics = _located(
            model_input=model_input,
            diagnostics=result.binding_diagnostics,
            cleaned=outcome.cleaned_sql or "",
        )
    if proof is not None and proof.output_proven:
        inferred = proof.fixed_columns
        has_star = True
    return CompiledModel(
        key=CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name=model_name),
        deps=tuple(
            CompiledObjectKey(resource_type=CompiledResourceType(kind), name=name)
            for kind, name in deps
        ),
        name=model_name,
        relative_path=model_input.model_file.relative_path,
        query_sql=model_input.query_sql,
        config=model_input.config,
        destination=build_model_relation_target(model_input=model_input, model_name=model_name),
        references=model_input.references,
        schema_entry=model_input.schema_entry,
        inferred_columns=inferred,
        fast_lineage_columns=lineage,
        fast_lineage_has_star=has_star,
        fast_lineage_star_resolved=star_resolved,
        authored_sql=model_input.model_file.contents,
        authored_query_sql=model_input.model_file.query_sql,
        output_column_locations=model_input.model_file.output_column_locations,
        extract_implicit_alias_columns=model_input.model_file.extract_implicit_alias_columns,
        macro_deps=macro_deps,
        enum_declarations=model_input.enum_declarations,
        constant_declarations=model_input.constant_declarations,
        enum_columns=model_input.enum_columns,
        binding_diagnostics=diagnostics,
        binding_validated=validated,
        dynamic_column_contract=proof,
        rejected_sql_analysis_opt_out=model_input.rejected_sql_analysis_opt_out,
    )


def dynamic_fallback_columns(
    rows: list[tuple[str, str | None, str]] | None,
) -> tuple[InferredColumn, ...] | None:
    """A failed analysis's parse-mode column rows as inferred columns."""

    if rows is None:
        return None
    return tuple(
        InferredColumn(name=name, type=data_type, nullability=InferredNullability(nullability))
        for name, data_type, nullability in rows
    )


def _located(
    *, model_input: ModelInput, diagnostics: tuple[SqlBindingDiagnostic, ...], cleaned: str
) -> tuple[CompilerDiagnostic, ...]:
    if not diagnostics:
        return ()
    expansion: CompiledSqlExpansion | None = model_input.sql_expansion
    path: Path = model_input.model_file.relative_path
    located: list[
        tuple[str, str, str, int | None, int | None, tuple[int, int, int | None, int | None] | None]
    ] = _native.locate_model_binding_diagnostics(
        [
            (item.code, item.message, item.line, item.column, item.start, item.end, item.severity)
            for item in diagnostics
        ],
        (model_input.model_file.contents, model_input.model_file.query_sql, cleaned),
        None if expansion is None else (expansion.expanded_sql, _pass_rows(expansion)),
    )
    return tuple(
        CompilerDiagnostic(
            phase=DiagnosticPhase.COMPILE,
            severity=severity,
            code=code,
            message=message,
            resource_type=CompiledResourceType.MODEL,
            resource_name=model_input.model_file.file_path.stem,
            path=path,
            line=line,
            column=column,
            location=None
            if span is None
            else SourceLocation(
                path=path, line=span[0], column=span[1], end_line=span[2], end_column=span[3]
            ),
        )
        for code, message, severity, line, column, span in located
    )


def _pass_rows(expansion: CompiledSqlExpansion) -> list[list[tuple[int, int, int, int]]]:
    return [list(map(_span_row, spans)) for spans in expansion.passes]


def _span_row(span: ExpansionSpan) -> tuple[int, int, int, int]:
    return (span.source_start, span.source_end, span.output_start, span.output_end)
