"""Validate compiled model contracts."""

from __future__ import annotations

from sqlbuild.adapter.contract.types import TypeDialect
from sqlbuild.compiler.compile.models import CompiledProject, CompilerDiagnostic
from sqlbuild.compiler.contracts._helpers.evaluation import (
    python_model_contract_diagnostics,
    requires_contract_evaluation,
)
from sqlbuild.compiler.contracts.main._evaluate_native_model_contracts import (
    evaluate_native_model_contracts,
)
from sqlbuild.compiler.contracts.models import ContractValidationResult
from sqlbuild.compiler.frontier.main.native_stage_enabled import native_stage_enabled
from sqlbuild.compiler.frontier.main.report_native_answer import report_native_answer
from sqlbuild.compiler.frontier.types import NativeStage
from sqlbuild.spec.contracts.types import ColumnContractMode


def evaluate_model_contracts(
    *,
    project: CompiledProject,
    dialect: TypeDialect | str | None = None,
) -> ContractValidationResult:
    """Evaluate model header column contracts against inferred output columns."""

    if native_stage_enabled(NativeStage.CONTRACTS):
        native_result: ContractValidationResult | None = evaluate_native_model_contracts(
            project=project, dialect=dialect
        )
        if native_result is not None:
            report_native_answer(stage=NativeStage.CONTRACTS, kind="contract_validations")
            return native_result
    mode: ColumnContractMode = project.settings.column_contract_mode
    if not any(requires_contract_evaluation(model=model, mode=mode) for model in project.models):
        return ContractValidationResult(diagnostics=())

    diagnostics: list[CompilerDiagnostic] = []
    for model in project.models:
        if requires_contract_evaluation(model=model, mode=mode):
            diagnostics.extend(
                python_model_contract_diagnostics(model=model, mode=mode, dialect=dialect)
            )
    return ContractValidationResult(diagnostics=tuple(diagnostics))
