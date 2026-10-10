"""Model contract diagnostics built by the native engine, materialised as Python builds them."""

from __future__ import annotations

import sqlbuild._native as _native
from sqlbuild.adapter.contract.types import TypeDialect
from sqlbuild.compiler.compile.models import (
    CompiledModel,
    CompiledProject,
    CompilerDiagnostic,
    DynamicColumnContractProof,
    RelatedLocation,
)
from sqlbuild.compiler.compile.types import (
    CompiledResourceType,
    DiagnosticPhase,
    DiagnosticSeverity,
)
from sqlbuild.compiler.contracts._helpers.output_locations import (
    output_column_location,
    output_related_locations,
)
from sqlbuild.compiler.contracts.models import ContractValidationResult
from sqlbuild.compiler.lineage.types import InferredNullability
from sqlbuild.spec.contracts.models import SchemaColumn, SchemaModelEntry, SourceLocation
from sqlbuild.spec.contracts.types import ColumnContractMode

type _DeclaredRow = tuple[str, str | None, bool, bool]
type _SchemaRow = tuple[list[_DeclaredRow], list[tuple[str, str]], bool, bool]
type _ProofRow = tuple[bool, str | None, list[tuple[str, str | None]]]
type _ModelRow = tuple[
    str,
    str | None,
    _SchemaRow | None,
    list[tuple[str, str | None, bool]] | None,
    bool,
    _ProofRow | None,
    list[str],
]
type _DiagnosticRow = tuple[
    str, bool, str, str | None, int | None, str | None, tuple[str, str] | None, str
]


def native_model_contracts(
    *, project: CompiledProject, dialect: TypeDialect | str | None
) -> ContractValidationResult:
    """Return every model's column contract diagnostics, in model order."""

    mode: ColumnContractMode = project.settings.column_contract_mode
    outcomes: list[list[_DiagnosticRow]] = _native.evaluate_native_model_contracts(
        (
            str(dialect or "generic"),
            mode == ColumnContractMode.IMPLICIT,
            [_model_row(model) for model in project.models],
        )
    )
    diagnostics: list[CompilerDiagnostic] = []
    for model, rows in zip(project.models, outcomes, strict=True):
        diagnostics.extend(_diagnostic(model=model, row=row) for row in rows)
    return ContractValidationResult(diagnostics=tuple(diagnostics))


def _model_row(model: CompiledModel) -> _ModelRow:
    contract: object = model.config.values.get("contract")
    return (
        model.name,
        contract if isinstance(contract, str) else None,
        _schema_row(model=model, schema=model.schema_entry),
        None
        if model.inferred_columns is None
        else [
            (column.name, column.type, column.nullability == InferredNullability.NULLABLE)
            for column in model.inferred_columns
        ],
        bool(model.fast_lineage_has_star),
        _proof_row(model.dynamic_column_contract),
        list(model.unchecked_output_columns),
    )


def _schema_row(*, model: CompiledModel, schema: SchemaModelEntry | None) -> _SchemaRow | None:
    if schema is None:
        return None
    named_schema: bool = schema.model_schema is not None
    return (
        [
            (
                column.name,
                column.type,
                column.nullable is False,
                named_schema and _declared_outside_model(model=model, column=column),
            )
            for column in schema.columns
        ],
        [(family.name, family.type) for family in schema.dynamic_columns],
        bool(schema.type_enforcement),
        named_schema,
    )


def _declared_outside_model(*, model: CompiledModel, column: SchemaColumn) -> bool:
    return column.location is not None and column.location.path != model.relative_path


def _proof_row(proof: DynamicColumnContractProof | None) -> _ProofRow | None:
    if proof is None:
        return None
    return (
        bool(proof.output_proven),
        proof.failure_reason,
        [(family.name, family.inferred_type) for family in proof.families],
    )


def _diagnostic(*, model: CompiledModel, row: _DiagnosticRow) -> CompilerDiagnostic:
    code, is_error, message, column_name, declared_index, output_column, related, help_text = row
    return CompilerDiagnostic(
        phase=DiagnosticPhase.CONTRACT,
        severity=DiagnosticSeverity.ERROR if is_error else DiagnosticSeverity.WARNING,
        code=code,
        message=message,
        resource_type=CompiledResourceType.MODEL,
        resource_name=model.name,
        column_name=column_name,
        path=model.relative_path,
        location=_location(model=model, declared_index=declared_index, output_column=output_column),
        related_locations=_related_locations(model=model, related=related),
        help=help_text,
    )


def _location(
    *, model: CompiledModel, declared_index: int | None, output_column: str | None
) -> SourceLocation | None:
    if declared_index is not None and model.schema_entry is not None:
        return model.schema_entry.columns[declared_index].location
    if output_column is not None:
        return output_column_location(model=model, column_name=output_column)
    return None


def _related_locations(
    *, model: CompiledModel, related: tuple[str, str] | None
) -> tuple[RelatedLocation, ...]:
    if related is None:
        return ()
    column_name, message = related
    return output_related_locations(model=model, column_name=column_name, message=message)
