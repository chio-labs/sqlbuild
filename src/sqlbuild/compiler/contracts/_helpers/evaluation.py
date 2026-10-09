"""Which models need contract evaluation, and Python's evaluation of one model."""

from __future__ import annotations

from sqlbuild.adapter.contract.types import TypeDialect
from sqlbuild.compiler.compile.models import CompiledModel, CompilerDiagnostic
from sqlbuild.compiler.contracts._helpers.columns import collect_model_column_contract_diagnostics
from sqlbuild.compiler.planner.types import ContractPolicy
from sqlbuild.spec.contracts.types import ColumnContractMode


def requires_contract_evaluation(*, model: CompiledModel, mode: ColumnContractMode) -> bool:
    """Whether the model declares a shape to validate or enforces declared types."""

    if declared_shape_validation_is_active(model=model, mode=mode):
        return True
    return model.schema_entry is not None and bool(model.schema_entry.type_enforcement)


def declared_shape_validation_is_active(*, model: CompiledModel, mode: ColumnContractMode) -> bool:
    """Whether the model's declared columns are validated against its inferred output."""

    contract: object = model.config.values.get("contract")
    if contract == ContractPolicy.ENFORCED:
        return True
    if contract == ContractPolicy.NONE:
        return False
    return mode == ColumnContractMode.IMPLICIT and bool(
        model.schema_entry is not None and model.schema_entry.columns
    )


def python_model_contract_diagnostics(
    *, model: CompiledModel, mode: ColumnContractMode, dialect: TypeDialect | str | None
) -> tuple[CompilerDiagnostic, ...]:
    """Python's contract diagnostics for one model that requires evaluation."""

    return collect_model_column_contract_diagnostics(
        model=model,
        validate_declared_shape=declared_shape_validation_is_active(model=model, mode=mode),
        dialect=dialect,
    )
