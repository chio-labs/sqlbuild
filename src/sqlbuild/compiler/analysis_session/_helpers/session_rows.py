"""Plain rows crossing into and out of the native model analysis session."""

from __future__ import annotations

from collections.abc import Mapping

from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.compiler.analysis_session.models import NativeModelAnalysisRequest
from sqlbuild.compiler.analysis_session.types import (
    ColumnRow,
    DeferredRow,
    DiagnosticRow,
    FamilyRow,
    LineageItem,
    ProofRow,
    ShapeRows,
)
from sqlbuild.compiler.compile.classes.python_model_analysis import PythonModelAnalysis
from sqlbuild.compiler.compile.models import (
    CompactLineageFacts,
    CompiledLineageColumnFact,
    CompiledLineageSourceFact,
    DynamicColumnContractProof,
    DynamicColumnFamilyProof,
    InferredColumn,
    PolyglotAnalysisResult,
)
from sqlbuild.compiler.lineage.types import InferredNullability
from sqlbuild.compiler.sql_analysis.constants import CASE_SENSITIVE_BINDING_DIALECTS
from sqlbuild.compiler.sql_analysis.models import SqlBindingDiagnostic
from sqlbuild.spec.contracts.models import SchemaDynamicColumnFamily


def shape_rows(shapes: Mapping[str, Mapping[str, object]]) -> ShapeRows | None:
    """`{relation: {column: value}}` as ordered rows, or None when a value is not text."""

    rows: ShapeRows = []
    for name, shape in shapes.items():
        columns: list[tuple[str, str]] = []
        for column, value in shape.items():
            if not isinstance(column, str) or not isinstance(value, str):
                return None
            columns.append((column, str(value)))
        rows.append((name, columns))
    return rows


def session_request(
    *,
    request: NativeModelAnalysisRequest,
    python: PythonModelAnalysis,
    schemas: Mapping[str, Mapping[str, str]],
) -> tuple[object, ...] | None:
    """The session request, or None when a shape cannot cross as text."""

    profile: ExpressionInferenceProfile = request.inference_profile
    shapes: tuple[ShapeRows | None, ...] = (
        shape_rows(request.column_types_by_table),
        shape_rows(request.column_nullability_by_table),
        shape_rows(request.complete_binding_schemas),
        shape_rows(schemas),
    )
    if any(rows is None for rows in shapes):
        return None
    return (
        profile.sql_analysis_dialect or "generic",
        case_sensitive_shapes(profile=profile, dialect=profile.sql_analysis_dialect),
        list(profile.function_return_types.items()),
        request.rich_type_inference,
        *shapes,
        family_rows(request.dynamic_families_by_table),
        python.model_rows(),
    )


def contract_proof(row: ProofRow | None) -> DynamicColumnContractProof | None:
    """A native dynamic pivot proof as Python's, None when absent or left to Python."""

    if row is None:
        return None
    output_proven, columns, families, input_relations, failure_reason, bare = row
    return DynamicColumnContractProof(
        output_proven=output_proven,
        fixed_columns=inferred_columns(columns) or (),
        families=tuple(
            DynamicColumnFamilyProof(name=name, inferred_type=inferred_type)
            for name, inferred_type in families
        ),
        input_relations=tuple(input_relations),
        failure_reason=failure_reason,
        bare_dynamic_pivot=bare,
    )


def case_sensitive_shapes(*, profile: ExpressionInferenceProfile, dialect: str | None) -> bool:
    """Python's `inferred_binding_shape` test for keeping authored identifier quoting."""

    return not profile.quoted_identifiers_ignore_case and dialect in CASE_SENSITIVE_BINDING_DIALECTS


def column_rows(columns: tuple[InferredColumn, ...] | None) -> list[ColumnRow] | None:
    if columns is None:
        return None
    return [(column.name, column.type, str(column.nullability)) for column in columns]


def diagnostic_rows(diagnostics: tuple[SqlBindingDiagnostic, ...]) -> list[DiagnosticRow]:
    return [
        (
            diagnostic.code,
            diagnostic.message,
            diagnostic.line,
            diagnostic.column,
            diagnostic.start,
            diagnostic.end,
            diagnostic.severity,
        )
        for diagnostic in diagnostics
    ]


def deferred_row(*, model: int, analysis: PolyglotAnalysisResult) -> DeferredRow:
    """Python's answer to one deferral, without the lineage Python keeps."""

    return (
        model,
        analysis.analysis_succeeded,
        column_rows(analysis.columns),
        analysis.has_star,
        analysis.star_resolved,
        diagnostic_rows(analysis.binding_diagnostics),
        analysis.binding_validated,
    )


def inferred_columns(rows: list[ColumnRow] | None) -> tuple[InferredColumn, ...] | None:
    return shared_inferred_columns(rows=rows, shared={})


def shared_inferred_columns(
    *, rows: list[ColumnRow] | None, shared: dict[ColumnRow, InferredColumn]
) -> tuple[InferredColumn, ...] | None:
    """Columns as Python's analysis shares them: one object per distinct column value."""

    if rows is None:
        return None
    return tuple(_shared_column(row=row, shared=shared) for row in rows)


def _shared_column(*, row: ColumnRow, shared: dict[ColumnRow, InferredColumn]) -> InferredColumn:
    column: InferredColumn | None = shared.get(row)
    if column is None:
        name, data_type, nullability = row
        column = InferredColumn(
            name=name, type=data_type, nullability=InferredNullability(nullability)
        )
        shared[row] = column
    return column


def binding_diagnostics(rows: list[DiagnosticRow]) -> tuple[SqlBindingDiagnostic, ...]:
    return tuple(SqlBindingDiagnostic(*row) for row in rows)


def compact_lineage(rows: list[LineageItem]) -> CompactLineageFacts:
    """Native lineage rows as Python's compact facts over a per-model string pool."""

    pool: dict[str, int] = {}
    compact_rows: list[tuple[int, int, int, tuple[tuple[int, int, int], ...]]] = []
    for output_column, transform_code, confidence_code, sources in rows:
        source_indexes: list[tuple[int, int, int]] = []
        for resource_type, resource_name, column_name in sources:
            source_indexes.append(
                (
                    pool.setdefault(resource_type, len(pool)),
                    pool.setdefault(resource_name, len(pool)),
                    pool.setdefault(column_name, len(pool)),
                )
            )
        compact_rows.append(
            (
                pool.setdefault(output_column, len(pool)),
                transform_code,
                confidence_code,
                tuple(source_indexes),
            )
        )
    return CompactLineageFacts(string_pool=tuple(pool), rows=tuple(compact_rows))


def lineage_facts(rows: list[LineageItem]) -> tuple[CompiledLineageColumnFact, ...]:
    """Native lineage rows as the plain facts Python's re-analysis returns."""

    return tuple(
        CompiledLineageColumnFact(
            output_column=output_column,
            upstream_columns=_source_facts(sources),
            transform_kind=CompactLineageFacts.transform_kind(transform_code),
            confidence=CompactLineageFacts.confidence(confidence_code),
        )
        for output_column, transform_code, confidence_code, sources in rows
    )


def _source_facts(sources: list[tuple[str, str, str]]) -> tuple[CompiledLineageSourceFact, ...]:
    return tuple(
        CompiledLineageSourceFact(
            resource_type=resource_type, resource_name=resource_name, column_name=column_name
        )
        for resource_type, resource_name, column_name in sources
    )


def family_rows(
    families_by_table: dict[str, tuple[SchemaDynamicColumnFamily, ...]],
) -> list[tuple[str, list[FamilyRow]]]:
    """Declared dynamic families by relation, as native request rows."""

    return [(name, _family_rows(families)) for name, families in families_by_table.items()]


def _family_rows(families: tuple[SchemaDynamicColumnFamily, ...]) -> list[FamilyRow]:
    return [PythonModelAnalysis.family_row(family) for family in families]
