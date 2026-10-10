"""Plain rows crossing into and out of the native model analysis session."""

from __future__ import annotations

from collections.abc import Mapping

from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.compiler.analysis_session._helpers.profile_rows import (
    case_sensitive_shapes,
    nullability_rule_rows,
)
from sqlbuild.compiler.analysis_session.models import NativeModelAnalysisRequest
from sqlbuild.compiler.analysis_session.types import (
    ColumnRow,
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
)
from sqlbuild.compiler.lineage.types import InferredNullability
from sqlbuild.compiler.sql_analysis.models import SqlBindingDiagnostic
from sqlbuild.spec.contracts.models import SchemaDynamicColumnFamily


def shape_rows(shapes: Mapping[str, Mapping[str, str]]) -> ShapeRows:
    """`{relation: {column: value}}` as ordered rows; discovery rejects non-text names and types."""

    return [
        (name, [(column, str(value)) for column, value in shape.items()])
        for name, shape in shapes.items()
    ]


def session_request(
    *,
    request: NativeModelAnalysisRequest,
    python: PythonModelAnalysis,
    schemas: Mapping[str, Mapping[str, str]],
) -> tuple[object, ...]:
    """The session request."""

    profile: ExpressionInferenceProfile = request.inference_profile
    shapes: tuple[ShapeRows, ...] = (
        shape_rows(request.column_types_by_table),
        shape_rows(request.column_nullability_by_table),
        shape_rows(request.complete_binding_schemas),
        shape_rows(schemas),
    )
    return (
        profile.sql_analysis_dialect or "generic",
        case_sensitive_shapes(profile=profile, dialect=profile.sql_analysis_dialect),
        list(profile.function_return_types.items()),
        nullability_rule_rows(profile),
        request.rich_type_inference,
        *shapes,
        family_rows(request.dynamic_families_by_table),
        python.model_rows(),
    )


def contract_proof(row: ProofRow | None) -> DynamicColumnContractProof | None:
    """A native dynamic pivot proof as Python's, None when absent."""

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


def inferred_columns(rows: list[ColumnRow] | None) -> tuple[InferredColumn, ...] | None:
    if rows is None:
        return None
    return tuple(
        InferredColumn(name=name, type=data_type, nullability=InferredNullability(nullability))
        for name, data_type, nullability in rows
    )


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
