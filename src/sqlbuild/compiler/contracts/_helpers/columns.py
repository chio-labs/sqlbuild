"""Model column contract validation."""

from __future__ import annotations

from sqlbuild.adapter.contract.types import TypeDialect
from sqlbuild.adapter.type_system.main.types_equal import types_equal
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import (
    CompiledModel,
    InferredColumn,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.contracts.constants import NOT_NULL_AUDIT_NAME
from sqlbuild.compiler.diagnostics.models import CompilerDiagnostic, RelatedLocation
from sqlbuild.compiler.diagnostics.types import DiagnosticPhase, DiagnosticSeverity
from sqlbuild.compiler.lineage.types import InferredNullability
from sqlbuild.compiler.planner.types import ContractPolicy
from sqlbuild.spec.contracts.models import SchemaColumn, SourceLocation

_MISSING_COLUMN_CODE: str = "K001"
_TYPE_MISMATCH_CODE: str = "K002"
_UNKNOWN_TYPE_CODE: str = "K003"
_NULLABILITY_MISMATCH_CODE: str = "K004"
_EXTRA_COLUMN_CODE: str = "K005"
_MISSING_DECLARATIONS_CODE: str = "K006"


def collect_model_column_contract_diagnostics(
    *,
    model: CompiledModel,
    dialect: TypeDialect | str | None = None,
) -> tuple[CompilerDiagnostic, ...]:
    """Collect diagnostics for one compiled model's declared column contract."""

    contract_enforced: bool = model.config.values.get("contract") == ContractPolicy.ENFORCED
    if model.schema_entry is None or not model.schema_entry.columns:
        if contract_enforced:
            return (_missing_declarations_diagnostic(model),)
        return ()
    if model.inferred_columns is None:
        return ()

    inferred_by_name: dict[str, InferredColumn] = {
        column.name: column for column in model.inferred_columns
    }
    diagnostics: list[CompilerDiagnostic] = []
    if contract_enforced:
        diagnostics.extend(_extra_column_diagnostics(model=model))
    declared_column: SchemaColumn
    for declared_column in model.schema_entry.columns:
        inferred_column: InferredColumn | None = inferred_by_name.get(declared_column.name)
        if inferred_column is None:
            diagnostics.append(_missing_column_diagnostic(model=model, column=declared_column))
            continue
        diagnostics.extend(
            _nullability_diagnostics(
                model=model,
                declared_column=declared_column,
                inferred_column=inferred_column,
            )
        )
        if declared_column.type is None:
            continue
        diagnostics.extend(
            _type_diagnostics(
                model=model,
                declared_column=declared_column,
                inferred_column=inferred_column,
                dialect=dialect,
                contract_enforced=contract_enforced,
            )
        )
    return tuple(diagnostics)


def _missing_declarations_diagnostic(model: CompiledModel) -> CompilerDiagnostic:
    return CompilerDiagnostic(
        phase=DiagnosticPhase.CONTRACT,
        severity=DiagnosticSeverity.ERROR,
        code=_MISSING_DECLARATIONS_CODE,
        message=f"model '{model.name}' has contract enforced but declares no columns",
        resource_type=CompiledResourceType.MODEL,
        resource_name=model.name,
        path=model.relative_path,
        help="add MODEL(columns (...)) or set contract none for this model",
    )


def _extra_column_diagnostics(model: CompiledModel) -> tuple[CompilerDiagnostic, ...]:
    if model.schema_entry is None or model.inferred_columns is None:
        return ()
    declared_names: set[str] = {column.name for column in model.schema_entry.columns}
    diagnostics: list[CompilerDiagnostic] = []
    inferred_column: InferredColumn
    for inferred_column in model.inferred_columns:
        if inferred_column.name in declared_names:
            continue
        diagnostics.append(
            CompilerDiagnostic(
                phase=DiagnosticPhase.CONTRACT,
                severity=DiagnosticSeverity.ERROR,
                code=_EXTRA_COLUMN_CODE,
                message=(
                    f"column '{inferred_column.name}' is not declared in enforced contract "
                    f"for model '{model.name}'"
                ),
                resource_type=CompiledResourceType.MODEL,
                resource_name=model.name,
                column_name=inferred_column.name,
                path=model.relative_path,
                location=model.output_column_locations.get(inferred_column.name),
                help="add the column to MODEL(columns) or remove it from the SELECT list",
            )
        )
    return tuple(diagnostics)


def _nullability_diagnostics(
    *,
    model: CompiledModel,
    declared_column: SchemaColumn,
    inferred_column: InferredColumn,
) -> tuple[CompilerDiagnostic, ...]:
    if not _declares_not_null(declared_column):
        return ()
    if inferred_column.nullability != InferredNullability.NULLABLE:
        return ()
    return (
        CompilerDiagnostic(
            phase=DiagnosticPhase.CONTRACT,
            severity=DiagnosticSeverity.ERROR,
            code=_NULLABILITY_MISMATCH_CODE,
            message=f"column '{declared_column.name}' is declared non-null but may be nullable",
            resource_type=CompiledResourceType.MODEL,
            resource_name=model.name,
            column_name=declared_column.name,
            path=model.relative_path,
            location=declared_column.location,
            related_locations=_output_related_locations(
                model=model,
                column_name=declared_column.name,
                message="output expression proven nullable",
            ),
            help="use COALESCE, filter nulls explicitly, or remove the non-null contract",
        ),
    )


def _declares_not_null(column: SchemaColumn) -> bool:
    if column.nullable is False:
        return True
    return any(audit.definition_name == NOT_NULL_AUDIT_NAME for audit in column.audits)


def _missing_column_diagnostic(*, model: CompiledModel, column: SchemaColumn) -> CompilerDiagnostic:
    return CompilerDiagnostic(
        phase=DiagnosticPhase.CONTRACT,
        severity=DiagnosticSeverity.ERROR,
        code=_MISSING_COLUMN_CODE,
        message=f"required column '{column.name}' missing from model output",
        resource_type=CompiledResourceType.MODEL,
        resource_name=model.name,
        column_name=column.name,
        path=model.relative_path,
        location=column.location,
        help=f"add {column.name} to the SELECT list or remove it from MODEL(columns)",
    )


def _type_diagnostics(
    *,
    model: CompiledModel,
    declared_column: SchemaColumn,
    inferred_column: InferredColumn,
    dialect: TypeDialect | str | None,
    contract_enforced: bool,
) -> tuple[CompilerDiagnostic, ...]:
    declared_type: str | None = declared_column.type
    if declared_type is None:
        raise CompileInputError(
            f"model '{model.name}' column '{declared_column.name}' reached type validation "
            "without a declared type",
            code="P003",
        )
    type_enforcement: bool = model.schema_entry is not None and bool(
        model.schema_entry.type_enforcement
    )
    if inferred_column.type is None:
        if not type_enforcement:
            return ()
        return (
            CompilerDiagnostic(
                phase=DiagnosticPhase.CONTRACT,
                severity=DiagnosticSeverity.WARNING,
                code=_UNKNOWN_TYPE_CODE,
                message=(
                    f"column '{declared_column.name}' type could not be proven against "
                    f"declared {declared_type}"
                ),
                resource_type=CompiledResourceType.MODEL,
                resource_name=model.name,
                column_name=declared_column.name,
                path=model.relative_path,
                location=declared_column.location,
                related_locations=_output_related_locations(
                    model=model,
                    column_name=declared_column.name,
                    message="output expression with unproven type",
                ),
                help="add an explicit CAST if this contract should be checked statically",
            ),
        )

    if types_equal(left=declared_type, right=inferred_column.type, dialect=dialect):
        return ()

    return (
        CompilerDiagnostic(
            phase=DiagnosticPhase.CONTRACT,
            severity=DiagnosticSeverity.ERROR
            if type_enforcement or contract_enforced
            else DiagnosticSeverity.WARNING,
            code=_TYPE_MISMATCH_CODE,
            message=(
                f"column '{declared_column.name}' inferred as {inferred_column.type} "
                f"but contract declares {declared_type}"
            ),
            resource_type=CompiledResourceType.MODEL,
            resource_name=model.name,
            column_name=declared_column.name,
            path=model.relative_path,
            location=declared_column.location,
            related_locations=_output_related_locations(
                model=model,
                column_name=declared_column.name,
                message=f"inferred {inferred_column.type}",
            ),
            help="change the declared type or cast the expression explicitly",
        ),
    )


def _output_related_locations(
    *, model: CompiledModel, column_name: str, message: str
) -> tuple[RelatedLocation, ...]:
    location: SourceLocation | None = model.output_column_locations.get(column_name)
    if location is None:
        return ()
    return (RelatedLocation(label="output", location=location, message=message),)
