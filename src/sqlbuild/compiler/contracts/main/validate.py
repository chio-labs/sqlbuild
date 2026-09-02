"""Validate compiled model contracts."""

from __future__ import annotations

from sqlbuild.adapter.contract.types import TypeDialect
from sqlbuild.compiler.compile.models import CompiledModel, CompiledProject, CompilerDiagnostic
from sqlbuild.compiler.contracts._helpers.columns import collect_model_column_contract_diagnostics
from sqlbuild.compiler.contracts.models import ContractValidationResult
from sqlbuild.compiler.planner.types import ContractPolicy
from sqlbuild.spec.contracts.types import ColumnContractMode


def evaluate_model_contracts(
    *,
    project: CompiledProject,
    dialect: TypeDialect | str | None = None,
) -> ContractValidationResult:
    """Evaluate model header column contracts against inferred output columns."""

    if not any(
        _requires_contract_evaluation(model=model, mode=project.settings.column_contract_mode)
        for model in project.models
    ):
        return ContractValidationResult(diagnostics=())

    diagnostics: list[CompilerDiagnostic] = []
    for model in project.models:
        if _requires_contract_evaluation(model=model, mode=project.settings.column_contract_mode):
            diagnostics.extend(
                collect_model_column_contract_diagnostics(
                    model=model,
                    validate_declared_shape=_declared_shape_validation_is_active(
                        model=model,
                        mode=project.settings.column_contract_mode,
                    ),
                    dialect=dialect,
                )
            )
    return ContractValidationResult(diagnostics=tuple(diagnostics))


def _requires_contract_evaluation(*, model: CompiledModel, mode: ColumnContractMode) -> bool:
    if _declared_shape_validation_is_active(model=model, mode=mode):
        return True
    return model.schema_entry is not None and bool(model.schema_entry.type_enforcement)


def _declared_shape_validation_is_active(*, model: CompiledModel, mode: ColumnContractMode) -> bool:
    contract: object = model.config.values.get("contract")
    if contract == ContractPolicy.ENFORCED:
        return True
    if contract == ContractPolicy.NONE:
        return False
    return mode == ColumnContractMode.IMPLICIT and bool(
        model.schema_entry is not None and model.schema_entry.columns
    )
