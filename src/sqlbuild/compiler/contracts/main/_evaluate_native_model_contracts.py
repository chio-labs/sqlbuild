"""Evaluate model contracts natively for the preview compiler engine."""

from __future__ import annotations

from sqlbuild.adapter.contract.types import TypeDialect
from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.contracts._helpers.native_contracts import native_model_contracts
from sqlbuild.compiler.contracts.models import ContractValidationResult


def evaluate_native_model_contracts(
    *, project: CompiledProject, dialect: TypeDialect | str | None
) -> ContractValidationResult | None:
    """Return the contract diagnostics, or None where Python must evaluate the contracts."""

    return native_model_contracts(project=project, dialect=dialect)
