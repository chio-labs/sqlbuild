"""Evaluate model contracts natively."""

from __future__ import annotations

from sqlbuild.adapter.contract.types import TypeDialect
from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.contracts._helpers.native_contracts import native_model_contracts
from sqlbuild.compiler.contracts.models import ContractValidationResult


def evaluate_native_model_contracts(
    *, project: CompiledProject, dialect: TypeDialect | str | None
) -> ContractValidationResult:
    """Return the contract diagnostics; Python evaluates only the models native defers."""

    return native_model_contracts(project=project, dialect=dialect)
