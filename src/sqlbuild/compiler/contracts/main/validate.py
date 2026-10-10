"""Validate compiled model contracts."""

from __future__ import annotations

from sqlbuild.adapter.contract.types import TypeDialect
from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.contracts.main._evaluate_native_model_contracts import (
    evaluate_native_model_contracts,
)
from sqlbuild.compiler.contracts.models import ContractValidationResult


def evaluate_model_contracts(
    *,
    project: CompiledProject,
    dialect: TypeDialect | str | None = None,
) -> ContractValidationResult:
    """Evaluate model header column contracts against inferred output columns."""

    return evaluate_native_model_contracts(project=project, dialect=dialect)
