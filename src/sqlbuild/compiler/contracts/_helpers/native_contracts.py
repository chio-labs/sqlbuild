"""Model contract diagnostics built by the native engine, materialised as Python builds them."""

from __future__ import annotations

import sqlbuild._native as _native
from sqlbuild.adapter.contract.types import TypeDialect
from sqlbuild.compiler.compile.models import (
    CompilerDiagnostic,
    RelatedLocation,
)
from sqlbuild.compiler.compile.types import (
    CompiledModelView,
    CompiledProjectView,
    CompiledResourceType,
    DiagnosticPhase,
    DiagnosticSeverity,
)
from sqlbuild.compiler.compiled_project.main.compiled_project_facts import compiled_project_facts
from sqlbuild.compiler.contracts._helpers.output_locations import (
    output_column_location,
    output_related_locations,
)
from sqlbuild.compiler.contracts.models import ContractValidationResult
from sqlbuild.spec.contracts.models import SourceLocation
from sqlbuild.spec.contracts.types import ColumnContractMode

type _DiagnosticRow = tuple[
    str, bool, str, str | None, int | None, str | None, tuple[str, str] | None, str
]


def native_model_contracts(
    *, project: CompiledProjectView, dialect: TypeDialect | str | None
) -> ContractValidationResult:
    """Return every model's column contract diagnostics, read from the owner, in model order."""

    mode: ColumnContractMode = project.settings.column_contract_mode
    outcomes: dict[str, list[_DiagnosticRow]] = dict(
        _native.evaluate_project_model_contracts(
            (str(dialect or "generic"), mode == ColumnContractMode.IMPLICIT),
            compiled_project_facts(project),
        )
    )
    diagnostics: list[CompilerDiagnostic] = []
    for model in project.models:
        diagnostics.extend(
            _diagnostic(model=model, row=row) for row in outcomes.get(model.name, ())
        )
    return ContractValidationResult(diagnostics=tuple(diagnostics))


def _diagnostic(*, model: CompiledModelView, row: _DiagnosticRow) -> CompilerDiagnostic:
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
    *, model: CompiledModelView, declared_index: int | None, output_column: str | None
) -> SourceLocation | None:
    if declared_index is not None and model.schema_entry is not None:
        return model.schema_entry.columns[declared_index].location
    if output_column is not None:
        return output_column_location(model=model, column_name=output_column)
    return None


def _related_locations(
    *, model: CompiledModelView, related: tuple[str, str] | None
) -> tuple[RelatedLocation, ...]:
    if related is None:
        return ()
    column_name, message = related
    return output_related_locations(model=model, column_name=column_name, message=message)
