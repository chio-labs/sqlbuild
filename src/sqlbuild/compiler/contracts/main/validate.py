"""Validate compiled model contracts."""

from __future__ import annotations

from sqlbuild.adapter.shared.types import TypeDialect
from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.contracts.helpers.columns import validate_model_column_contracts
from sqlbuild.compiler.contracts.models import ContractValidationResult
from sqlbuild.compiler.diagnostics.models import CompilerDiagnostic


def validate_model_contracts(
    project: CompiledProject,
    *,
    dialect: TypeDialect | str | None = None,
) -> ContractValidationResult:
    """Validate model header column contracts against inferred output columns."""

    diagnostics: list[CompilerDiagnostic] = []
    for model in project.models:
        diagnostics.extend(validate_model_column_contracts(model, dialect=dialect))
    return ContractValidationResult(diagnostics=tuple(diagnostics))
