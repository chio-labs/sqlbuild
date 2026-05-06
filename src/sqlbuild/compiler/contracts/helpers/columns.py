"""Model column contract validation."""

from __future__ import annotations

from sqlbuild.adapter.shared.type_normalization import types_equal
from sqlbuild.adapter.shared.types import TypeDialect
from sqlbuild.compiler.compile.models import CompiledModel, InferredColumn
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.diagnostics.models import CompilerDiagnostic, RelatedLocation
from sqlbuild.compiler.diagnostics.types import DiagnosticPhase, DiagnosticSeverity
from sqlbuild.spec.models.schema import SchemaColumn, SourceLocation

_MISSING_COLUMN_CODE: str = "K001"
_TYPE_MISMATCH_CODE: str = "K002"
_UNKNOWN_TYPE_CODE: str = "K003"


def validate_model_column_contracts(
    model: CompiledModel,
    *,
    dialect: TypeDialect | str | None = None,
) -> tuple[CompilerDiagnostic, ...]:
    """Validate one compiled model's declared column contract."""

    if model.schema_entry is None or not model.schema_entry.columns:
        return ()
    if model.inferred_columns is None:
        return ()

    inferred_by_name: dict[str, InferredColumn] = {
        column.name: column for column in model.inferred_columns
    }
    diagnostics: list[CompilerDiagnostic] = []
    declared_column: SchemaColumn
    for declared_column in model.schema_entry.columns:
        inferred_column: InferredColumn | None = inferred_by_name.get(declared_column.name)
        if inferred_column is None:
            diagnostics.append(_missing_column_diagnostic(model, declared_column))
            continue
        if declared_column.type is None:
            continue
        diagnostics.extend(
            _type_diagnostics(
                model=model,
                declared_column=declared_column,
                inferred_column=inferred_column,
                dialect=dialect,
            )
        )
    return tuple(diagnostics)


def _missing_column_diagnostic(model: CompiledModel, column: SchemaColumn) -> CompilerDiagnostic:
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
) -> tuple[CompilerDiagnostic, ...]:
    assert declared_column.type is not None
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
                    f"declared {declared_column.type}"
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

    if types_equal(left=declared_column.type, right=inferred_column.type, dialect=dialect):
        return ()

    return (
        CompilerDiagnostic(
            phase=DiagnosticPhase.CONTRACT,
            severity=DiagnosticSeverity.ERROR if type_enforcement else DiagnosticSeverity.WARNING,
            code=_TYPE_MISMATCH_CODE,
            message=(
                f"column '{declared_column.name}' inferred as {inferred_column.type} "
                f"but contract declares {declared_column.type}"
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
