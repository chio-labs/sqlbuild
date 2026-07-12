"""Validate compiled model contracts."""

from __future__ import annotations

from sqlbuild.adapter.types import TypeDialect
from sqlbuild.compiler.compile.models.core import CompiledProject
from sqlbuild.compiler.contracts.helpers.columns import collect_model_column_contract_diagnostics
from sqlbuild.compiler.contracts.models import ContractValidationResult
from sqlbuild.compiler.diagnostics.models import CompilerDiagnostic


def evaluate_model_contracts(
    *,
    project: CompiledProject,
    dialect: TypeDialect | str | None = None,
) -> ContractValidationResult:
    """Evaluate model header column contracts against inferred output columns."""

    if not any(
        model.config.values.get("contract") == "enforced"
        or (model.schema_entry is not None and model.schema_entry.columns)
        for model in project.models
    ):
        return ContractValidationResult(diagnostics=())

    diagnostics: list[CompilerDiagnostic] = []
    for model in project.models:
        diagnostics.extend(collect_model_column_contract_diagnostics(model=model, dialect=dialect))
    return ContractValidationResult(diagnostics=tuple(diagnostics))
